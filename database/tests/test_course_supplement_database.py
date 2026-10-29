"""격리 PostgreSQL에서 보충 적재·목차 갱신을 검증한다. 임베딩 응답만 대체한다."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.database import course_curriculum
from src.database.ingestion.course_supplement import insert_approved, insert_catalog_approved, prepare
from src.database.vectors import resource_vectors
from tests.test_course_supplement import external_course


class CourseSupplementDatabaseTests(unittest.TestCase):
    def setUp(self):
        url = os.environ.get('EMPLOYEE_FORM_TEST_DB_URL', '')
        if not url:
            self.skipTest('An isolated local test DB is required')
        params = conninfo_to_dict(url)
        if params.get('host') != '127.0.0.1' or not params.get('dbname', '').startswith('growpath_employee_form_test_'):
            raise ValueError('Refuse course writes outside the isolated local test DB')
        self.c = psycopg.connect(url, row_factory=dict_row, connect_timeout=5)
        self.addCleanup(self.c.close)
        self.addCleanup(self.c.rollback)
        self.skills = self.c.execute('SELECT skill_id,name,category FROM public.skill_tags ORDER BY skill_id').fetchall()
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.fake = [1.0] + [0.0] * (resource_vectors.DIMENSIONS - 1)
        self.api = self.enterContext(patch.object(resource_vectors, 'embed_texts',
                                                side_effect=lambda texts, **kw: [self.fake for _ in texts]))

    def fixture(self, source='WEB_INFLEARN'):
        row = external_course(source)
        key = str(uuid4().int % 10**12 + 10**12)
        slug = 'fastapi-' + key
        url = (f'https://www.inflearn.com/course/{slug}?cid={key}' if source == 'WEB_INFLEARN'
               else f'https://opentutorials.org/course/{key}')
        now = datetime.now(timezone.utc)
        row.update(external_key=key, fetched_at=now, matches={30: ['FastAPI/Django']})
        row['fields'].update(course_id=source.removeprefix('WEB_') + '_' + key,
                             platform='Inflearn' if source == 'WEB_INFLEARN' else '생활코딩',
                             url=url, source_url=url, source_verified_at=now)
        row['raw'].update(source_id=key, url=url)
        if source == 'WEB_INFLEARN':
            row['raw']['course_info'].update(id=int(key), slug=slug)
            for index, lesson in enumerate(row['raw']['lessons'], 1):
                lesson.update(id=index, runtime=1800)
        else:
            for index, lesson in enumerate(row['raw']['lessons'], 1):
                lesson['url'] = url + '/' + str(index)
        return row

    def saved(self, row):
        return self.c.execute('SELECT * FROM public.courses WHERE course_id=%s',
                              (row['fields']['course_id'],)).fetchone()

    def assert_absent(self, row):
        rid = row['fields']['course_id']
        self.assertIsNone(self.saved(row))
        for query in (
            'SELECT 1 FROM public.course_skills WHERE course_id=%s',
            "SELECT 1 FROM growpath_meta.catalog_api_sources WHERE resource_type='courses' AND entity_key=%s",
            "SELECT 1 FROM public.learning_resource_embeddings WHERE resource_type='courses' AND resource_id=%s",
        ):
            self.assertIsNone(self.c.execute(query, (rid,)).fetchone())

    def test_both_insert_paths_persist_time_outline_source_and_vector_and_reject_duplicates(self):
        for insert in (insert_approved, insert_catalog_approved):
            with self.subTest(path=insert.__name__):
                row = self.fixture()
                result = insert(self.c, [row], self.skills, source_root=self.root)
                saved = self.saved(row)
                self.assertEqual(result['inserted_courses'], 1)
                self.assertEqual(saved['duration_seconds'], 3600)
                self.assertEqual(saved['duration_kind'], 'video')
                self.assertIsNone(saved['estimated_duration_seconds'])
                self.assertEqual(saved['duration_provenance']['status'], 'confirmed')
                self.assertEqual(saved['curriculum']['coverage'], 'public_outline')
                self.assertEqual(saved['curriculum']['item_count'], 2)
                raw = self.c.execute("SELECT payload FROM growpath_meta.catalog_api_sources WHERE resource_type='courses' AND entity_key=%s",
                                     (row['fields']['course_id'],)).fetchone()['payload']
                self.assertEqual(raw, row['raw'])
                key = ('courses', row['fields']['course_id'])
                self.assertTrue(resource_vectors.is_current(resource_vectors.sources(self.c)[key], resource_vectors.stored(self.c)[key]))
                self.api.assert_called_once()
                self.api.reset_mock()
                with self.assertRaisesRegex(ValueError, '중복'):
                    insert(self.c, [row], self.skills, source_root=self.root)
                self.api.assert_not_called()

    def test_missing_video_runtime_is_stored_as_estimate_instead_of_confirmed_time(self):
        row = self.fixture()
        for lesson in row['raw']['lessons']:
            lesson.pop('runtime')
        insert_approved(self.c, [row], self.skills, source_root=self.root)
        saved = self.saved(row)
        self.assertIsNone(saved['duration_seconds'])
        self.assertEqual(saved['estimated_duration_seconds'], 2400)
        self.assertEqual(saved['duration_provenance']['status'], 'estimated')
        self.assertEqual(saved['duration_provenance']['missing_video_durations'], 2)

    def test_embedding_failure_rolls_back_courses_links_sources_and_vectors(self):
        rows = [self.fixture(), self.fixture()]
        self.api.side_effect = RuntimeError('simulated embedding failure')
        with self.assertRaisesRegex(RuntimeError, 'simulated embedding failure'), self.c.transaction():
            insert_approved(self.c, rows, self.skills, source_root=self.root)
        self.api.assert_called_once()
        for row in rows:
            self.assert_absent(row)

    def test_bad_cache_rejects_whole_batch_before_writes_or_embedding(self):
        rows = [self.fixture(), self.fixture('WEB_OPENTUTORIALS')]
        (self.root / 'outline.html').write_text('bad cache', encoding='utf-8')
        rows[1]['raw'].update(html_path='outline.html', html_sha256='0' * 64)
        for operation in (
            lambda: prepare(self.c, rows, source_root=self.root),
            lambda: insert_approved(self.c, rows, self.skills, source_root=self.root),
        ):
            with self.assertRaisesRegex(ValueError, 'checksum'):
                operation()
            for row in rows:
                self.assert_absent(row)
        self.api.assert_not_called()

    def test_sample_backfill_upgrades_when_verified_html_arrives_and_is_repeatable(self):
        row = self.fixture('WEB_OPENTUTORIALS')
        key = row['external_key']
        html = ''.join(f'<a class="depth_1" href="/course/{key}/{i}">{title}</a>'
                       for i, title in enumerate(('장고 앱', '장고 라우팅', '장고 테스트'), 1))
        row['raw'].update(html_path='outline.html', html_sha256=hashlib.sha256(html.encode()).hexdigest())
        rid = row['fields']['course_id']
        insert_approved(self.c, [row], self.skills, source_root=self.root)
        initial = self.saved(row)
        self.assertEqual(initial['curriculum']['coverage'], 'sample')
        self.api.reset_mock()
        path = self.root / 'outline.html'
        path.write_text(html, encoding='utf-8')
        preview = course_curriculum.backfill(self.c, source_root=self.root)
        self.assertGreaterEqual(preview['changed_count'], 1)
        self.assertEqual(self.saved(row)['curriculum'], initial['curriculum'])
        course_curriculum.backfill(self.c, apply=True, source_root=self.root)
        updated = self.saved(row)
        self.assertEqual(updated['curriculum']['coverage'], 'public_outline')
        self.assertEqual(updated['curriculum']['item_count'], 3)
        self.assertEqual({k: v for k, v in updated.items() if k != 'curriculum'},
                         {k: v for k, v in initial.items() if k != 'curriculum'})
        self.assertEqual(course_curriculum.backfill(self.c, apply=True, source_root=self.root)['changed_count'], 0)
        path.unlink()
        self.assertEqual(course_curriculum.backfill(self.c, source_root=self.root)['changed_count'], 0)
        self.assertEqual(self.c.execute("SELECT payload FROM growpath_meta.catalog_api_sources WHERE resource_type='courses' AND entity_key=%s",
                                       (rid,)).fetchone()['payload'], row['raw'])
        self.api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
