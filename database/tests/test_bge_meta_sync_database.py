"""일회용 PostgreSQL에서 자료·회사생활·스킬 보정 경로의 벡터·검증 기록 동시 저장을 검사한다.

실제 SQL·JOIN·해시·트랜잭션을 실행하고 임베딩 응답과 강좌 사용 가능 판정만 모의 처리한다.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from src.database.course_skill_corrections import apply_corrections
from src.database.ingestion import knowledge_documents as importer
from src.database.vectors import resource_vectors as resources
from src.shared.bge_embeddings import ACCEPTED_PROTOCOLS, IndexedEmbedding

VECTOR = [1.0] + [0.0] * 1023
FP16, FP32 = ACCEPTED_PROTOCOLS
TOKENS = 11
COURSE = 'INFLEARN_113593'
CATEGORY = '수자원공사 정보'
ROOT = Path(__file__).resolve().parents[2]
META_DDL = '''
CREATE SCHEMA growpath_bge_meta;
CREATE TABLE growpath_bge_meta.inputs (
    kind text NOT NULL, source_id text NOT NULL, source_sha256 text NOT NULL,
    actual_input_sha256 text NOT NULL, protocol text NOT NULL, model_revision text NOT NULL,
    token_count integer NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, source_id)
);
CREATE SCHEMA growpath_meta;
CREATE TABLE growpath_meta.catalog_api_sources (
    resource_type text, entity_key text, source text, payload jsonb, fetched_at timestamptz
);
'''


def indexed(texts, client=None):
    return [IndexedEmbedding(VECTOR[:], FP32, TOKENS) for _ in texts]


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class BgeMetaSyncDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_url = os.environ.get('BGE_META_TEST_DB_URL', '')
        if not cls.db_url:
            raise unittest.SkipTest('BGE_META_TEST_DB_URL의 일회용 DB가 필요합니다')
        params = conninfo_to_dict(cls.db_url)
        if not params.get('dbname', '').startswith('growpath_bge_meta_test_'):
            raise ValueError('growpath_bge_meta_test_ 전용 DB 외의 연결을 거절합니다')
        cls.admin = psycopg.connect(cls.db_url, autocommit=True, row_factory=dict_row)
        cls.addClassCleanup(cls.admin.close)
        if cls.admin.execute("SELECT to_regclass('public.courses') AS name").fetchone()['name']:
            raise ValueError('기존 표가 있는 DB를 덮어쓰지 않습니다')
        for name in ('01_erd_schema.sql', '02_app_ext.sql'):
            cls.admin.execute((ROOT / 'backend/db' / name).read_text(encoding='utf-8'), prepare=False)
        cls.admin.execute('DROP TABLE public.learning_resource_embeddings CASCADE')
        cls.admin.execute(META_DDL, prepare=False)
        cls.admin.execute(resources.DDL, prepare=False)
        knowledge_ddl = (ROOT / 'database/src/database/migrations/022_knowledge_documents.sql').read_text(encoding='utf-8')
        cls.admin.execute(knowledge_ddl.replace("'text-embedding-3-small'", "'BAAI/bge-m3'").replace('1536', '1024'),
                          prepare=False)

        from sqlalchemy import create_engine
        from sqlalchemy.engine import URL
        from sqlalchemy.pool import NullPool

        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql+psycopg://test:test@127.0.0.1:1/test'}):
            from app import db, bge_knowledge_search, llm
            from app.services import resource_rag
            from tools import verify_bge_database
        cls.knowledge, cls.llm, cls.rag, cls.verifier = bge_knowledge_search, llm, resource_rag, verify_bge_database
        cls.engine = create_engine(URL.create('postgresql+psycopg', database=params['dbname']),
                                   creator=lambda: psycopg.connect(cls.db_url), poolclass=NullPool)
        cls.addClassCleanup(cls.engine.dispose)
        engine_patch = patch.object(db, 'engine', cls.engine)
        engine_patch.start()
        cls.addClassCleanup(engine_patch.stop)

    def setUp(self):
        self.enterContext(patch('src.shared.catalog_eligibility.eligible_keys',
                                return_value=({('courses', COURSE)}, {})))
        self.admin.execute('''TRUNCATE public.learning_resource_embeddings, growpath_bge_meta.inputs,
            knowledge.chunks, knowledge.documents, app_ext.resource_meta, public.course_skills,
            public.courses, public.skill_tags CASCADE''', prepare=False)
        self.admin.execute("INSERT INTO public.skill_tags(skill_id,name,category) VALUES (1,'Python','IT/Tech'),(2,'SQL','IT/Tech')")
        self.admin.execute('''INSERT INTO public.courses(course_id,title,url,cost,platform,syllabus_summary)
            VALUES (%s,'강좌','https://example.test/a',1000,'INFLEARN','첫 소개')''', (COURSE,))
        self.admin.execute('INSERT INTO public.course_skills VALUES (%s,1)', (COURSE,))
        self.admin.execute('''INSERT INTO app_ext.resource_meta(resource_key,resource_type,course_id,cost_won)
            VALUES (%s,'course',%s,1000)''', (COURSE, COURSE))
        self.admin.execute("INSERT INTO knowledge.documents(document_id,category,title,document_kind) VALUES ('d1',%s,'문서','report')", (CATEGORY,))

    # 자료(강좌) 경로 -----------------------------------------------------------
    def embed_resources(self, side_effect=indexed):
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, \
             patch.object(resources, 'embed_for_index', side_effect=side_effect):
            return resources.embed(conn)

    def candidates(self):
        return self.rag.search_vectors('courses', [COURSE], VECTOR, 5, False)

    def verify(self):
        return self.verifier.verify(check_counts=False)

    def course_state(self):
        return (self.admin.execute("""SELECT input_sha256, embedding::text AS embedding, updated_at
                    FROM public.learning_resource_embeddings WHERE resource_type='courses' AND resource_id=%s""", (COURSE,)).fetchone(),
                self.admin.execute("SELECT * FROM growpath_bge_meta.inputs WHERE kind='courses' AND source_id=%s", (COURSE,)).fetchone())

    def set_summary(self, text):
        self.admin.execute('UPDATE public.courses SET syllabus_summary=%s WHERE course_id=%s', (text, COURSE))

    def reject_writes(self, table, condition):
        self.admin.execute(f'ALTER TABLE {table} ADD CONSTRAINT reject_test_write CHECK ({condition}) NOT VALID')
        self.addCleanup(self.admin.execute, f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS reject_test_write')

    def allow_writes(self, table):
        self.admin.execute(f'ALTER TABLE {table} DROP CONSTRAINT reject_test_write')

    def test_resource_refresh_keeps_candidate_verifies_and_retry_is_noop(self):
        self.assertEqual(self.embed_resources()['embedded_count'], 3)  # 스킬 2개 + 강좌 1개
        self.assertEqual(len(self.candidates()), 1)
        self.set_summary('바뀐 소개')
        self.assertEqual(self.embed_resources()['embedded_count'], 1)
        self.assertEqual(len(self.candidates()), 1)
        self.verify()
        before = self.course_state()
        self.assertEqual(self.embed_resources()['embedded_count'], 0)
        self.assertEqual(self.course_state(), before)
        self.assertEqual((before[1]['protocol'], before[1]['token_count']), (FP32, TOKENS))

    def test_resource_write_failures_roll_back_vector_and_metadata(self):
        for table, condition in (('growpath_bge_meta.inputs', "kind<>'courses'"),
                                 ('public.learning_resource_embeddings', "resource_type<>'courses'")):
            with self.subTest(table=table):
                self.embed_resources()
                before = self.course_state()
                self.set_summary(f'{table} 실패 시도')
                self.reject_writes(table, condition)
                with self.assertRaises(psycopg.errors.CheckViolation):
                    self.embed_resources()
                self.allow_writes(table)
                self.assertEqual(self.course_state(), before)

    def test_resource_embedding_failure_preserves_stored_values(self):
        self.embed_resources()
        before = self.course_state()
        self.set_summary('임베딩 실패 시도')

        def fail(texts, client=None):
            raise RuntimeError('model down')

        with self.assertRaisesRegex(RuntimeError, 'model down'):
            self.embed_resources(fail)
        self.assertEqual(self.course_state(), before)

    def test_resource_source_change_during_embedding_rolls_back(self):
        self.embed_resources()
        before = self.course_state()
        self.set_summary('임베딩 전 소개')

        def concurrent(texts, client=None):
            self.set_summary('임베딩 도중 바뀐 소개')
            return indexed(texts)

        with self.assertRaisesRegex(ValueError, 'sources changed'):
            self.embed_resources(concurrent)
        self.assertEqual(self.course_state(), before)

    def test_resource_truncated_input_keeps_separate_hashes(self):
        self.set_summary('가' * 9000)
        self.embed_resources()
        meta = self.course_state()[1]
        self.assertNotEqual(meta['source_sha256'], meta['actual_input_sha256'])
        self.assertEqual(self.embed_resources()['embedded_count'], 0)
        self.verify()

    def test_resource_missing_metadata_is_repaired(self):
        self.embed_resources()
        self.admin.execute("DELETE FROM growpath_bge_meta.inputs WHERE kind='courses'")
        self.assertEqual(self.candidates(), [])
        self.assertEqual(self.embed_resources()['embedded_count'], 1)
        self.assertEqual(len(self.candidates()), 1)

    def test_database_without_metadata_table_is_refused_without_creating_one(self):
        self.embed_resources()
        before = self.course_state()[0]
        self.admin.execute('ALTER TABLE growpath_bge_meta.inputs RENAME TO inputs_hidden')
        self.addCleanup(self.admin.execute, 'ALTER TABLE growpath_bge_meta.inputs_hidden RENAME TO inputs')
        self.set_summary('메타 표 없음')
        with patch.object(resources, 'embed_for_index') as api:
            with self.assertRaisesRegex(ValueError, 'Restore the shared BGE-M3 database'):
                self.embed_resources(api)
            api.assert_not_called()
        self.assertIsNone(self.admin.execute("SELECT to_regclass('growpath_bge_meta.inputs') AS id").fetchone()['id'])
        self.assertEqual(self.admin.execute("""SELECT input_sha256, embedding::text AS embedding, updated_at
            FROM public.learning_resource_embeddings WHERE resource_type='courses'""").fetchone(), before)

    def test_shared_fp16_records_stay_current_and_only_changed_row_becomes_fp32(self):
        self.embed_resources()
        self.admin.execute('UPDATE growpath_bge_meta.inputs SET protocol=%s, token_count=1', (FP16,))
        self.assertEqual(self.embed_resources()['embedded_count'], 0)
        self.verify()
        self.set_summary('재색인 소개')
        self.assertEqual(self.embed_resources()['embedded_count'], 1)
        rows = self.admin.execute('SELECT kind, protocol, token_count FROM growpath_bge_meta.inputs ORDER BY kind').fetchall()
        self.assertEqual(rows, [{'kind': 'courses', 'protocol': FP32, 'token_count': TOKENS},
                                {'kind': 'skills', 'protocol': FP16, 'token_count': 1},
                                {'kind': 'skills', 'protocol': FP16, 'token_count': 1}])
        self.verify()

    # 회사·생활 경로 ------------------------------------------------------------
    def add_chunk(self, identifier, order, text):
        self.admin.execute('''INSERT INTO knowledge.chunks(chunk_id,document_id,display_order,chunk_text,chunk_text_sha256,is_virtual,metadata)
            VALUES (%s,'d1',%s,%s,%s,false,'{}')''', (identifier, order, text, sha(text)))

    def change_chunk(self, identifier, text):
        self.admin.execute('''UPDATE knowledge.chunks SET chunk_text=%s,chunk_text_sha256=%s,embedding=NULL,embedding_model=NULL,
            dimensions=NULL,input_sha256=NULL,embedded_at=NULL WHERE chunk_id=%s''', (text, sha(text), identifier))

    def ensure_chunks(self, side_effect=indexed):
        with patch.object(self.knowledge.embeddings, 'embed_for_index', side_effect=side_effect):
            return self.knowledge.ensure_vectors(self.knowledge.source_chunks())

    def search_chunks(self):
        with patch.object(self.knowledge.embeddings, 'embed', return_value=[VECTOR]):
            return self.knowledge.search('물 관리 질문', CATEGORY)

    def chunk_state(self):
        return (self.admin.execute('SELECT chunk_id,input_sha256,embedding::text AS embedding,embedded_at FROM knowledge.chunks ORDER BY chunk_id').fetchall(),
                self.admin.execute("SELECT * FROM growpath_bge_meta.inputs WHERE kind='knowledge' ORDER BY source_id").fetchall())

    def two_chunks(self):
        self.add_chunk('k1', 1, '첫 조각 물 관리')
        self.add_chunk('k2', 2, '둘째 조각 물 관리')
        self.ensure_chunks()

    def test_knowledge_refresh_search_verify_and_retry_is_noop(self):
        self.two_chunks()
        self.assertEqual(len(self.search_chunks()), 2)
        self.verify()
        self.change_chunk('k2', '바뀐 둘째 조각 물 관리')
        self.assertEqual(self.ensure_chunks(), 1)
        self.assertTrue(any(row['chunk_text'].startswith('바뀐') for row in self.search_chunks()))
        self.verify()
        self.assertEqual(self.ensure_chunks(), 0)
        self.assertEqual({(row['protocol'], row['token_count']) for row in self.chunk_state()[1]}, {(FP32, TOKENS)})

    def test_knowledge_second_row_failure_rolls_back_first_row(self):
        from sqlalchemy.exc import IntegrityError

        self.two_chunks()
        for table, condition in (('growpath_bge_meta.inputs', "NOT (kind='knowledge' AND source_id='k2')"),
                                 ('knowledge.chunks', "chunk_id<>'k2'")):
            with self.subTest(table=table):
                self.admin.execute("DELETE FROM growpath_bge_meta.inputs WHERE kind='knowledge'")
                before = self.chunk_state()
                self.reject_writes(table, condition)
                with self.assertRaises(IntegrityError):
                    self.ensure_chunks()
                self.allow_writes(table)
                self.assertEqual(self.chunk_state(), before)
                self.ensure_chunks()

    def test_knowledge_source_change_during_embedding_rolls_back_batch(self):
        self.two_chunks()
        self.admin.execute("DELETE FROM growpath_bge_meta.inputs WHERE kind='knowledge'")

        def concurrent(texts):
            self.change_chunk('k2', '임베딩 도중 바뀐 조각')
            return indexed(texts)

        with self.assertRaisesRegex(self.llm.LlmError, '자료 원문이 바뀌었어요'):
            self.ensure_chunks(concurrent)
        self.assertEqual(self.chunk_state()[1], [])

    # 회사·생활 적재 도구 --------------------------------------------------------
    def import_row(self, identifier='k3', order=3, text='가져오기 도구로 넣은 조각 물 관리'):
        return {'chunk_id': identifier, 'category': CATEGORY, 'document_id': 'd1', 'document_title': '문서',
                'document_kind': 'report', 'display_order': order, 'chunk_text': text,
                'chunk_text_sha256': sha(text), 'is_virtual': False}

    def run_import(self, rows, side_effect=indexed):
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, \
             patch.object(importer, 'embed_for_index', side_effect=side_effect), patch('builtins.print'):
            return importer.insert(conn, rows)

    def test_import_saves_metadata_so_search_and_verify_pass(self):
        self.two_chunks()
        self.assertEqual(self.run_import([self.import_row()])['embedded_chunks'], 1)
        meta = self.admin.execute("SELECT * FROM growpath_bge_meta.inputs WHERE kind='knowledge' AND source_id='k3'").fetchone()
        self.assertEqual((meta['protocol'], meta['token_count']), (FP32, TOKENS))
        self.assertEqual(len(self.search_chunks()), 3)
        self.verify()
        self.assertEqual(self.run_import([self.import_row()])['embedded_chunks'], 0)

    def test_import_repairs_missing_metadata_of_existing_vector(self):
        self.run_import([self.import_row()])
        self.admin.execute("DELETE FROM growpath_bge_meta.inputs WHERE kind='knowledge'")
        self.assertEqual(self.run_import([self.import_row()])['embedded_chunks'], 1)
        self.assertEqual(len(self.chunk_state()[1]), 1)

    def test_import_metadata_failure_rolls_back_chunk(self):
        self.reject_writes('growpath_bge_meta.inputs', "NOT (kind='knowledge' AND source_id='k4')")
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.run_import([self.import_row(), self.import_row('k4', 4, '실패할 조각')])
        self.assertEqual(self.chunk_state(), ([], []))

    # 강좌 스킬 보정 도구 --------------------------------------------------------
    def correction_plan(self):
        return {'corrections': [{'course_id': COURSE, 'title': '강좌', 'syllabus_sha256': sha('첫 소개'),
                                 'before_skill_ids': [1], 'after_skill_ids': [1, 2],
                                 'reason': '검토된 보정', 'evidence': '커리큘럼 근거'}]}

    def apply_plan(self, side_effect=indexed):
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, \
             patch.object(resources, 'embed_for_index', side_effect=side_effect):
            return apply_corrections(conn, self.correction_plan())

    def links(self):
        return [row['skill_id'] for row in self.admin.execute(
            'SELECT skill_id FROM public.course_skills WHERE course_id=%s ORDER BY skill_id', (COURSE,)).fetchall()]

    def test_correction_updates_links_vector_and_metadata_then_retry_is_noop(self):
        self.embed_resources()
        before = self.course_state()
        result = self.apply_plan()
        self.assertEqual((result['status'], result['embedded_count']), ('applied', 1))
        self.assertIn(resources.META_TABLE, result['changed_tables'])
        self.assertEqual(self.links(), [1, 2])
        after = self.course_state()
        self.assertNotEqual(after[0]['input_sha256'], before[0]['input_sha256'])
        self.assertEqual(after[1]['source_sha256'], after[0]['input_sha256'])
        self.assertEqual(len(self.candidates()), 1)
        self.verify()
        self.assertEqual(self.apply_plan()['status'], 'already_applied')

    def test_correction_failures_roll_back_links_vector_and_metadata(self):
        self.embed_resources()
        before = self.course_state()
        self.reject_writes('growpath_bge_meta.inputs', "kind<>'courses'")
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.apply_plan()
        self.allow_writes('growpath_bge_meta.inputs')
        self.assertEqual((self.links(), self.course_state()), ([1], before))

        def fail(texts, client=None):
            raise RuntimeError('model down')

        with self.assertRaisesRegex(RuntimeError, 'model down'):
            self.apply_plan(fail)
        self.assertEqual((self.links(), self.course_state()), ([1], before))

    def test_correction_rejects_existing_stale_metadata_before_changing_links(self):
        self.embed_resources()
        self.admin.execute("UPDATE growpath_bge_meta.inputs SET model_revision='old' WHERE kind='courses'")
        with self.assertRaisesRegex(ValueError, 'Existing stale vectors'):
            self.apply_plan()
        self.assertEqual(self.links(), [1])


if __name__ == '__main__':
    unittest.main()
