"""기본 412개와 야간 보강 2개 검증. 실제 적재 검사는 명시한 격리 DB에서만 실행한다."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from scripts import apply_internal_training as training


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.courses = training.read_packages()

    def test_all_three_packages_have_412_unique_courses(self):
        self.assertEqual([len(json.loads(p.read_text(encoding='utf-8'))['courses']) for p in training.DEFAULT_PACKAGES], [12, 394, 6])
        self.assertEqual(len(self.courses), 412)
        self.assertEqual(len({c['id'] for c in self.courses}), 412)
        self.assertEqual(sum(c['fee_won'] == 0 for c in self.courses), 126)

    def test_base_412_and_separate_night_two_form_414_unique_courses(self):
        night = training.read_packages([training.NIGHT_PACKAGE])
        combined = training.read_packages([*training.DEFAULT_PACKAGES, training.NIGHT_PACKAGE])
        self.assertEqual(len(night), 2)
        self.assertEqual(len(combined), 414)
        self.assertEqual(len({c['id'] for c in combined}), 414)
        self.assertEqual(sum(c['fee_won'] == 0 for c in combined), 128)
        self.assertNotIn(training.NIGHT_PACKAGE, training.default_packages())

    def test_night_metadata_and_duration_match_the_existing_supply_contract(self):
        raw = json.loads(training.NIGHT_PACKAGE.read_text(encoding='utf-8'))
        for course in training.read_packages([training.NIGHT_PACKAGE]):
            fields, meta = training.course_fields(course), training.meta_fields(course)
            self.assertEqual(course['difficulty'], 'INTERMEDIATE')
            self.assertEqual(fields['duration_provenance']['package_version'], raw['version'])
            self.assertEqual(fields['duration_seconds'], 60 * sum(u['minutes'] for u in course['units']))
            self.assertEqual(fields['duration_weeks'], 4)
            self.assertEqual(fields['cost'], meta['cost_won'])
            self.assertEqual(meta['note'], course['outcome'])
        self.assertEqual([sum(u['minutes'] for u in c['units']) for c in training.read_packages([training.NIGHT_PACKAGE])], [75, 65])

    def test_night_package_rejects_extra_or_duplicate_course_ids(self):
        package = json.loads(training.NIGHT_PACKAGE.read_text(encoding='utf-8'))
        package['courses'][1]['id'] = package['courses'][0]['id']
        with self.assertRaises(ValueError):
            training._night_courses(package)

    def test_no_legacy_promotion_or_external_mutations_in_packages(self):
        for path in training.DEFAULT_PACKAGES[:2]:
            self.assertEqual(set(json.loads(path.read_text(encoding='utf-8'))), {'schema_version', 'origin', 'courses'})
        free = json.loads(training.DEFAULT_PACKAGES[2].read_text(encoding='utf-8'))
        converted = training._free_courses(free)
        self.assertEqual(set(converted), {'schema_version', 'courses'})
        self.assertEqual([c['id'] for c in converted['courses']], [c['id'] for c in free['courses']])

    def test_free_course_source_changes_flow_to_shared_fields_without_duplicate_data(self):
        package = json.loads(training.DEFAULT_PACKAGES[2].read_text(encoding='utf-8'))
        package['courses'][0]['outcome'] = '검토자가 보강한 새 산출물'
        package['courses'][0]['units'][0]['minutes'] += 5
        course = training._free_courses(package)['courses'][0]
        self.assertIn('검토자가 보강한 새 산출물', training.course_fields(course)['syllabus_summary'])
        self.assertEqual(training.meta_fields(course)['note'], '검토자가 보강한 새 산출물')
        self.assertEqual(training.course_fields(course)['duration_seconds'], sum(u['minutes'] for u in course['units']) * 60)
        self.assertFalse((training.ROOT / 'config/internal_training_free_147.json').exists())

    def test_price_duration_url_and_nonreal_metadata_are_consistent(self):
        for course in self.courses:
            raw, meta = training.course_fields(course), training.meta_fields(course)
            self.assertEqual(raw['duration_seconds'], sum(u['minutes'] for u in course['units']) * 60)
            self.assertEqual(raw['cost'], meta['cost_won'])
            self.assertEqual(raw['url'], f"/resources/{course['id']}?view=curriculum")
            self.assertFalse(meta['is_real'])
            self.assertEqual(meta['source_label'], '사내교육')
        self.assertIsNone(training.course_fields(self.courses[0])['duration_weeks'])
        self.assertEqual(training.course_fields(self.courses[-1])['duration_weeks'], 4)

    def _read_changed(self, change):
        package = json.loads(training.DEFAULT_PACKAGES[0].read_text(encoding='utf-8'))
        change(package)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'courses.json'
            path.write_text(json.dumps(package), encoding='utf-8')
            return training.read_packages([path])

    def test_duplicate_id_unknown_sections_and_invalid_course_are_rejected(self):
        changes = [lambda p: p['courses'].append(deepcopy(p['courses'][0])),
                   lambda p: p.update(reviewed=[]),
                   lambda p: p['courses'][0].update(fee_won=-1),
                   lambda p: p['courses'][0].update(url='https://example.invalid/course'),
                   lambda p: p['courses'][0]['units'][0].update(minutes=0)]
        for change in changes:
            with self.subTest(change=changes.index(change)), self.assertRaises(ValueError):
                self._read_changed(change)

    def test_later_team_package_can_append_courses_without_changing_defaults(self):
        extra = deepcopy(self.courses[-1])
        extra.update(id='INTERNAL_CRASH_9999', url='/resources/INTERNAL_CRASH_9999?view=curriculum')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'extra.json'
            path.write_text(json.dumps(dict(schema_version='internal-training/v1', courses=[extra])), encoding='utf-8')
            courses = training.read_packages([*training.DEFAULT_PACKAGES, path])
        self.assertEqual(len(courses), 413)
        self.assertEqual(len(training.read_packages()), 412)

    def test_registered_team_package_is_loaded_by_default(self):
        extra = deepcopy(self.courses[-1])
        extra.update(id='INTERNAL_CRASH_9999', url='/resources/INTERNAL_CRASH_9999?view=curriculum')
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            names = []
            for path in training.DEFAULT_PACKAGES:
                (folder / path.name).write_bytes(path.read_bytes())
                names.append(path.name)
            (folder / 'additional_training.json').write_text(json.dumps(dict(schema_version='internal-training/v1', courses=[extra])), encoding='utf-8')
            index = folder / 'index.json'
            index.write_text(json.dumps(dict(schema_version='internal-training-index/v1', packages=names + ['additional_training.json'])), encoding='utf-8')
            with patch.object(training, 'PACKAGE_INDEX', index):
                self.assertEqual(len(training.read_packages()), 413)

    def test_vector_must_match_source_model_and_normalization(self):
        source = dict(hash='a' * 64, text='확인할 원문')
        row = dict(dimensions=1024, input_version=training.vectors.INPUT_VERSION, input_sha256=source['hash'],
                   actual_input_sha256=hashlib.sha256(source['text'].encode()).hexdigest(),
                   model_revision=training.PROVENANCE['model_revision'], protocol=training.ACCEPTED_PROTOCOLS[0],
                   token_count=4, vector=[1.] + [0.] * 1023)
        for protocol in training.ACCEPTED_PROTOCOLS:
            self.assertEqual(len(training._validate_vector(dict(row, protocol=protocol), source)), 1024)
        for change in ({'input_sha256': 'b' * 64}, {'actual_input_sha256': 'c' * 64},
                       {'model_revision': 'other'}, {'dimensions': 1536}, {'vector': [2.] + [0.] * 1023},
                       {'vector': [float('nan')] + [0.] * 1023}, {'token_count': 0}, {'protocol': 'unknown'}):
            with self.subTest(change=list(change)), self.assertRaises(ValueError):
                training._validate_vector(dict(row, **change), source)


def fingerprints(conn, ids: list[str], *, external: bool) -> dict:
    filters = {
        ('public', 'courses'): 'course_id <> ALL(%s)',
        ('public', 'course_skills'): 'course_id <> ALL(%s)',
        ('app_ext', 'resource_meta'): 'course_id IS NULL OR course_id <> ALL(%s)',
        ('public', 'learning_resource_embeddings'): "resource_type<>'courses' OR resource_id <> ALL(%s)",
        ('growpath_bge_meta', 'inputs'): "kind<>'courses' OR source_id <> ALL(%s)",
    }
    result = {}
    tables = conn.execute("""SELECT table_schema,table_name FROM information_schema.tables
        WHERE table_type='BASE TABLE' AND table_schema NOT IN ('pg_catalog','information_schema')
        ORDER BY table_schema,table_name""").fetchall()
    for row in tables:
        key = (row['table_schema'], row['table_name'])
        if not external and key not in filters:
            continue
        query = sql.SQL("SELECT count(*) AS n,md5(COALESCE(string_agg(v,'|' ORDER BY v),'')) AS hash FROM "
                        "(SELECT to_jsonb(t)::text AS v FROM {}.{} t{} ) q").format(
            sql.Identifier(key[0]), sql.Identifier(key[1]),
            sql.SQL(' WHERE ' + filters[key]) if external and key in filters else sql.SQL(''))
        result['.'.join(key)] = dict(conn.execute(query, (ids,) if external and key in filters else ()).fetchone())
    return result


@unittest.skipUnless(os.environ.get('INTERNAL_TRAINING_TEST_DSN'), '격리 DB를 명시하지 않음')
class IsolatedDatabaseTests(unittest.TestCase):
    def test_empty_install_retry_failures_and_vector_recovery(self):
        courses = training.read_packages()
        ids = [c['id'] for c in courses]
        cache = Path(os.environ['INTERNAL_TRAINING_VECTOR_CACHE'])
        events = []
        with psycopg.connect(os.environ['INTERNAL_TRAINING_TEST_DSN'], row_factory=dict_row, autocommit=True) as conn:
            self.assertTrue(conn.info.dbname.startswith('training147'))
            self.assertTrue(conn.info.host.startswith('course147-night-db-'))
            self.assertEqual(conn.execute('SELECT count(*) AS n FROM public.courses WHERE course_id=ANY(%s)', (ids,)).fetchone()['n'], 0)
            level_sql = """SELECT count(*) FILTER (WHERE difficulty='UPPER_INTERMEDIATE') AS reviewed,
                count(*) FILTER (WHERE difficulty_estimated) AS estimated FROM public.courses"""
            levels_before = conn.execute(level_sql).fetchone()
            self.assertEqual(dict(levels_before), dict(reviewed=85, estimated=615))
            outside = fingerprints(conn, ids, external=True)
            empty_state = fingerprints(conn, ids, external=False)
            schema_before = conn.execute("""SELECT md5(string_agg(pg_get_constraintdef(oid),'|' ORDER BY oid)) AS hash
                FROM pg_constraint WHERE connamespace NOT IN (SELECT oid FROM pg_namespace WHERE nspname='pg_catalog')""").fetchone()
            with patch.object(training, 'embed_for_index', side_effect=AssertionError('캐시 검사 중 추론 금지')):
                preview = training.install(conn, courses, vector_cache=cache, cache_only=True)
                self.assertEqual((preview['inserted'], preview['pending_vectors']), (412, 412))
                self.assertEqual(fingerprints(conn, ids, external=False), empty_state)
                events.append(dict(case='empty_preview_rollback', **preview))
                result = training.install(conn, courses, apply=True, vector_cache=cache, cache_only=True)
                self.assertEqual((result['inserted'], result['reused_vectors'], result['generated_vectors']), (412, 412, 0))
                events.append(dict(case='empty_to_412', **result))
                unchanged = fingerprints(conn, ids, external=False)
                for apply in (False, True):
                    retry = training.install(conn, courses, apply=apply, vector_cache=cache, cache_only=True)
                    self.assertEqual((retry['inserted'], retry['changed_courses'], retry['pending_vectors']), (0, 0, 0))
                    self.assertEqual(fingerprints(conn, ids, external=False), unchanged)
                    events.append(dict(case='retry', **retry))

                invalid = deepcopy(courses)
                invalid[0]['fee_won'] += 1
                invalid[-1]['skills'] = ['존재하지 않는 테스트 스킬']
                with self.assertRaisesRegex(ValueError, '등록되지 않은 스킬'):
                    training.install(conn, invalid, apply=True, refresh=True, vector_cache=cache, cache_only=True)
                self.assertEqual(fingerprints(conn, ids, external=False), unchanged)
                events.append(dict(case='late_error_atomic_rollback', passed=True))

                changed = deepcopy(courses)
                changed[0]['title'] += ' (검토 보강)'
                with self.assertRaisesRegex(ValueError, '원문 해시'):
                    training.install(conn, changed, apply=True, refresh=True, vector_cache=cache, cache_only=True)
                self.assertEqual(fingerprints(conn, ids, external=False), unchanged)
                events.append(dict(case='changed_source_rejects_old_vector', passed=True))

                rid = ids[-1]
                conn.execute("DELETE FROM public.learning_resource_embeddings WHERE resource_type='courses' AND resource_id=%s", (rid,))
                conn.execute("DELETE FROM growpath_bge_meta.inputs WHERE kind='courses' AND source_id=%s", (rid,))
                recovery = training.install(conn, courses, apply=True, vector_cache=cache, cache_only=True)
                self.assertEqual((recovery['pending_vectors'], recovery['reused_vectors']), (1, 1))
                events.append(dict(case='missing_vector_recovery', **recovery))
            self.assertEqual(fingerprints(conn, ids, external=True), outside)
            self.assertEqual(conn.execute(level_sql).fetchone(), levels_before)
            events.append(dict(case='difficulty_85_reviewed_615_estimated_preserved', **levels_before))
            schema_after = conn.execute("""SELECT md5(string_agg(pg_get_constraintdef(oid),'|' ORDER BY oid)) AS hash
                FROM pg_constraint WHERE connamespace NOT IN (SELECT oid FROM pg_namespace WHERE nspname='pg_catalog')""").fetchone()
            self.assertEqual(schema_before, schema_after)
            check = conn.execute('''SELECT count(*) AS n,count(*) FILTER (WHERE c.cost=m.cost_won) AS prices,
                count(*) FILTER (WHERE c.duration_seconds=round(m.hours*3600)) AS durations,
                count(*) FILTER (WHERE c.enrollment_period_type='unrestricted' AND c.recruitment_status='OPEN'
                    AND c.enrollment_start IS NULL AND c.enrollment_end IS NULL) AS periods,
                count(*) FILTER (WHERE c.url='/resources/'||c.course_id||'?view=curriculum') AS urls,
                count(*) FILTER (WHERE NOT m.is_real AND m.source_label='사내교육' AND m.content=c.syllabus_summary) AS meta
                FROM public.courses c JOIN app_ext.resource_meta m ON m.resource_key=c.course_id AND m.course_id=c.course_id
                WHERE c.course_id=ANY(%s)''', (ids,)).fetchone()
            self.assertEqual(set(check.values()), {412})
            events.append(dict(case='all_metadata_verified', **check))
            events.append(dict(case='external_rows_and_schema_unchanged', passed=True, tables=len(outside)))
        output = os.environ.get('INTERNAL_TRAINING_TEST_REPORT')
        if output:
            Path(output).write_text(json.dumps(events, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
