"""일회용 PostgreSQL에서 규정 벡터·메타 저장과 백엔드 읽기 계약을 검사한다."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from src.database.vectors import regulation_vectors as vectors


VECTOR = [1.0] + [0.0] * 1023
OTHER_VECTOR = [0.0, 1.0] + [0.0] * 1022
FIXTURE_TABLES = (
    'regulations.regulation_versions',
    'regulations.rag_chunks',
    'regulations.rag_chunk_embeddings',
    'growpath_bge_meta.inputs',
    'public.learning_resource_embeddings',
    'knowledge.chunks',
)


class RegulationVectorMetadataDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_url = os.environ.get('BGE_REGULATION_TEST_DB_URL', '')
        if not cls.db_url:
            raise unittest.SkipTest('BGE_REGULATION_TEST_DB_URL의 일회용 DB가 필요합니다')
        params = conninfo_to_dict(cls.db_url)
        if not params.get('dbname', '').startswith('growpath_regulation_test_'):
            raise ValueError('growpath_regulation_test_ 전용 DB 외의 연결을 거절합니다')
        from sqlalchemy import create_engine
        from sqlalchemy.engine import URL
        from sqlalchemy.pool import NullPool

        # embed()가 직접 commit하므로 기존 DB의 외부 rollback에 의존하지 않는다.
        with psycopg.connect(cls.db_url, row_factory=dict_row) as conn:
            existing = [name for name in FIXTURE_TABLES
                        if conn.execute('SELECT to_regclass(%s) AS name', (name,)).fetchone()['name']]
            if existing:
                raise ValueError('기존 표가 있는 DB를 덮어쓰지 않습니다: ' + ', '.join(existing))
            conn.execute('''
                CREATE EXTENSION IF NOT EXISTS vector;
                CREATE EXTENSION IF NOT EXISTS pgcrypto;
                CREATE SCHEMA IF NOT EXISTS regulations;
                CREATE SCHEMA IF NOT EXISTS knowledge;
                CREATE SCHEMA IF NOT EXISTS growpath_bge_meta;
                CREATE TABLE regulations.regulation_versions (
                    regulation_version_id text PRIMARY KEY,
                    review_status text NOT NULL,
                    availability_status text NOT NULL,
                    effective_from date,
                    effective_to date
                );
                CREATE TABLE regulations.rag_chunks (
                    rag_chunk_id varchar(64) PRIMARY KEY,
                    regulation_version_id text NOT NULL
                        REFERENCES regulations.regulation_versions,
                    context_path text NOT NULL,
                    chunk_text text NOT NULL,
                    search_status text NOT NULL
                );
                CREATE TABLE growpath_bge_meta.inputs (
                    kind text NOT NULL,
                    source_id text NOT NULL,
                    source_sha256 text NOT NULL,
                    actual_input_sha256 text NOT NULL,
                    protocol text NOT NULL,
                    model_revision text NOT NULL,
                    token_count integer NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (kind, source_id)
                );
                CREATE TABLE public.learning_resource_embeddings (
                    resource_type text, resource_id text, embedding_model text,
                    dimensions integer, embedding vector(1024),
                    input_version text, input_sha256 text
                );
                CREATE TABLE knowledge.chunks (
                    chunk_id text, embedding_model text, dimensions integer,
                    embedding vector(1024), input_sha256 text,
                    chunk_text_sha256 text, chunk_text text
                );
            ''', prepare=False)
            conn.execute(vectors.DDL, prepare=False)

        # 앱 기본 엔진은 연결하지 않고, 실제 SQL만 검사 전용 엔진으로 실행한다.
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql+psycopg://test:test@127.0.0.1:1/test'}):
            from app import db, bge_regulation_search
            from tools import verify_bge_database
        cls.backend = bge_regulation_search
        cls.verifier = verify_bge_database
        cls.engine = create_engine(
            URL.create('postgresql+psycopg', database=params['dbname']),
            creator=lambda: psycopg.connect(cls.db_url), poolclass=NullPool)
        cls.addClassCleanup(cls.engine.dispose)
        engine_patch = patch.object(db, 'engine', cls.engine)
        engine_patch.start()
        cls.addClassCleanup(engine_patch.stop)

    def setUp(self):
        self.conn = psycopg.connect(self.db_url, row_factory=dict_row)
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.conn.execute('''
            ALTER TABLE regulations.rag_chunk_embeddings
                DROP CONSTRAINT IF EXISTS reject_test_write;
            ALTER TABLE growpath_bge_meta.inputs
                DROP CONSTRAINT IF EXISTS reject_test_write;
            TRUNCATE regulations.rag_chunk_embeddings, growpath_bge_meta.inputs,
                regulations.rag_chunks, regulations.regulation_versions;
            INSERT INTO regulations.regulation_versions VALUES
                ('v1', 'approved', 'available', DATE '2020-01-01', NULL);
        ''', prepare=False)
        for identifier in ('r1', 'r2'):
            self.conn.execute('''INSERT INTO regulations.rag_chunks VALUES
                (%s, 'v1', %s, %s, 'active')''',
                (identifier, '취업규칙 > ' + identifier, identifier + ' 원문\n둘째 줄'))
        self.conn.commit()
        self.temp = self.enterContext(TemporaryDirectory())

    def _state(self):
        return {
            'vectors': self.conn.execute('''SELECT rag_chunk_id, embedding_model,
                dimensions, input_version, input_sha256, embedding::text,
                created_at, updated_at FROM regulations.rag_chunk_embeddings
                ORDER BY rag_chunk_id''').fetchall(),
            'meta': self.conn.execute('''SELECT * FROM growpath_bge_meta.inputs
                ORDER BY kind, source_id''').fetchall(),
        }

    def _embed(self):
        with patch.object(vectors, 'embed_texts',
                          side_effect=lambda texts: [VECTOR[:] for _ in texts]) as embed:
            result = vectors.embed(self.conn)
        self.conn.commit()
        return result, embed

    def _export(self, name='vectors.json'):
        path = Path(self.temp) / name
        result = vectors.export_vectors(self.conn, path)
        self.conn.commit()
        self.assertEqual(result['exported_vectors'], 2)
        return path

    def _backend_accepts_current_vectors(self):
        articles = {row['rag_chunk_id']: {
            'id': row['rag_chunk_id'], 'path': row['context_path'],
            'chunkText': row['chunk_text'],
        } for row in vectors.sources(self.conn)}
        self.conn.commit()
        with patch.object(self.backend.regstore, 'pool', return_value=list(articles.values())), \
             patch.object(self.backend.regstore, 'article', side_effect=articles.__getitem__), \
             patch.object(self.backend.hybrid_search, 'enabled', return_value=False), \
             patch.object(self.backend.embeddings, 'embed', return_value=[VECTOR]):
            results = self.backend.search('휴가 규정', 2, None)
        self.assertEqual({row['id'] for row in results}, set(articles))
        report = self.verifier.verify(check_counts=False)
        self.assertEqual(report['tables'][vectors.TABLE], {'total': 2, 'valid': 2})
        self.assertEqual(report['provenance'], {'total': 2, 'valid': 2})

    def _backend_ensure(self, vector=VECTOR):
        articles = {row['rag_chunk_id']: {
            'id': row['rag_chunk_id'], 'path': row['context_path'],
            'chunkText': row['chunk_text'],
        } for row in vectors.sources(self.conn)}
        self.conn.commit()
        with patch.object(self.backend.regstore, 'article', side_effect=articles.__getitem__), \
             patch.object(self.backend.embeddings, 'embed',
                          side_effect=lambda texts: [vector[:] for _ in texts]) as embed:
            result = self.backend.ensure_vectors(list(articles))
        return result, embed

    def test_backend_ensure_refreshes_real_sql_and_retry_is_noop(self):
        first, _ = self._backend_ensure()
        self.assertEqual(first, 2)
        self._backend_accepts_current_vectors()
        self.conn.execute("UPDATE regulations.rag_chunks SET chunk_text=%s WHERE rag_chunk_id='r1'",
                          ('백엔드 재색인 원문\n변경된 둘째 줄',))
        self.conn.commit()
        refreshed, embed = self._backend_ensure()
        self.assertEqual(refreshed, 1)
        embed.assert_called_once_with(['취업규칙 > r1\n\n백엔드 재색인 원문\n변경된 둘째 줄'])
        self._backend_accepts_current_vectors()
        before = self._state()
        retry, embed = self._backend_ensure()
        self.assertEqual(retry, 0)
        embed.assert_not_called()
        self.assertEqual(self._state(), before)

    def test_backend_ensure_sql_failures_roll_back_existing_batch(self):
        from sqlalchemy.exc import IntegrityError

        self._embed()
        self.conn.execute("UPDATE regulations.rag_chunks SET chunk_text=chunk_text || ' 백엔드 변경'")
        self.conn.commit()
        for table, identifier in ((vectors.META_TABLE, 'source_id'),
                                  (vectors.TABLE, 'rag_chunk_id')):
            with self.subTest(table=table):
                # 기존 두 행은 유지하되 r2의 새 INSERT/UPDATE만 실패하게 한다.
                self.conn.execute(f'''ALTER TABLE {table} ADD CONSTRAINT reject_test_write
                    CHECK ({identifier} <> 'r2') NOT VALID''')
                self.conn.commit()
                before = self._state()
                try:
                    with self.assertRaises(IntegrityError) as raised:
                        self._backend_ensure(vector=OTHER_VECTOR)
                    self.assertIsInstance(raised.exception.orig, psycopg.errors.CheckViolation)
                    self.assertEqual(self._state(), before)
                finally:
                    self.conn.rollback()
                    self.conn.execute(f'ALTER TABLE {table} DROP CONSTRAINT reject_test_write')
                    self.conn.commit()

    def test_source_refresh_is_accepted_by_backend_and_retry_is_noop(self):
        first, _ = self._embed()
        self.assertEqual(first['saved'], 2)
        self._backend_accepts_current_vectors()
        self.conn.execute("UPDATE regulations.rag_chunks SET chunk_text=%s WHERE rag_chunk_id='r1'",
                          ('변경된 원문\n새 둘째 줄',))
        self.conn.commit()
        refreshed, embed = self._embed()
        self.assertEqual(refreshed['saved'], 1)
        embed.assert_called_once_with(['취업규칙 > r1\n\n변경된 원문\n새 둘째 줄'])
        self._backend_accepts_current_vectors()
        before = self._state()
        retry, embed = self._embed()
        self.assertEqual(retry['saved'], 0)
        embed.assert_not_called()
        self.assertEqual(self._state(), before)

    def test_missing_or_invalid_metadata_is_repaired_by_reindexing(self):
        self._embed()
        invalid = (
            (None, None), ('source_sha256', '0' * 64),
            ('actual_input_sha256', '1' * 64), ('model_revision', 'old-revision'),
            ('protocol', 'old-protocol'), ('token_count', 0), ('token_count', 8193),
        )
        for index, (column, value) in enumerate(invalid):
            with self.subTest(column=column, value=value):
                if column is None:
                    self.conn.execute("DELETE FROM growpath_bge_meta.inputs WHERE source_id='r1'")
                else:
                    # 열 이름은 위의 고정된 검사 목록에서만 가져온다.
                    self.conn.execute(f"UPDATE growpath_bge_meta.inputs SET {column}=%s WHERE source_id='r1'",
                                      (value,))
                self.conn.commit()
                self.assertEqual(vectors.status(self.conn)['missing_or_stale_vectors'], 1)
                stale_export = Path(self.temp) / f'stale-{index}.json'
                with self.assertRaises(ValueError):
                    vectors.export_vectors(self.conn, stale_export)
                self.assertFalse(stale_export.exists())
                with self.assertRaises(ValueError):
                    self.verifier.verify(check_counts=False)
                repaired, embed = self._embed()
                self.assertEqual(repaired['saved'], 1)
                embed.assert_called_once()
                self._backend_accepts_current_vectors()

    def test_export_import_preserves_provenance_and_restores_search(self):
        self._embed()
        path = self._export()
        payload = json.loads(json.loads(path.read_text(encoding='utf-8'))['payload'])
        self.assertEqual(payload['format_version'], 2)
        self.assertEqual(payload['provenance'], vectors.PROVENANCE)
        self.conn.execute('TRUNCATE regulations.rag_chunk_embeddings, growpath_bge_meta.inputs')
        self.conn.commit()
        with patch.object(vectors, 'embed_texts') as embed, self.conn.transaction():
            imported = vectors.import_vectors(self.conn, path)
        embed.assert_not_called()
        self.assertEqual(imported['imported_vectors'], 2)
        self.conn.commit()
        self._backend_accepts_current_vectors()
        retry, embed = self._embed()
        self.assertEqual(retry['saved'], 0)
        embed.assert_not_called()

    def test_import_rejects_legacy_or_wrong_provenance_before_writes(self):
        self._embed()
        path = self._export()
        payload = json.loads(json.loads(path.read_text(encoding='utf-8'))['payload'])
        before = self._state()
        cases = [dict(payload, format_version=1)]
        for field in vectors.PROVENANCE:
            cases.append(dict(payload, provenance=dict(vectors.PROVENANCE, **{field: 'wrong'})))
        for index, invalid in enumerate(cases):
            with self.subTest(index=index):
                data = json.dumps(invalid, ensure_ascii=False, sort_keys=True)
                altered = Path(self.temp) / f'invalid-{index}.json'
                altered.write_text(json.dumps({'payload': data,
                    'sha256': hashlib.sha256(data.encode('utf-8')).hexdigest()}), encoding='utf-8')
                with patch.object(vectors, 'embed_texts') as embed:
                    with self.assertRaises(ValueError), self.conn.transaction():
                        vectors.import_vectors(self.conn, altered)
                embed.assert_not_called()
                self.assertEqual(self._state(), before)

    def _assert_import_write_failure_rolls_back_batch(self, path):
        for table, identifier in ((vectors.TABLE, 'rag_chunk_id'),
                                  (vectors.META_TABLE, 'source_id')):
            with self.subTest(table=table):
                self.conn.execute(f'''ALTER TABLE {table} ADD CONSTRAINT reject_test_write
                    CHECK ({identifier} <> 'r2') NOT VALID''')
                self.conn.commit()
                before = self._state()
                try:
                    with patch.object(vectors, 'embed_texts') as embed:
                        with self.assertRaises(psycopg.errors.CheckViolation):
                            vectors.import_vectors(self.conn, path)
                    embed.assert_not_called()
                    self.assertEqual(self._state(), before)
                finally:
                    self.conn.rollback()
                    self.conn.execute(f'ALTER TABLE {table} DROP CONSTRAINT reject_test_write')
                    self.conn.commit()

    def test_embed_sql_failures_roll_back_vector_and_metadata_batch(self):
        for table, identifier in ((vectors.TABLE, 'rag_chunk_id'),
                                  (vectors.META_TABLE, 'source_id')):
            with self.subTest(table=table):
                self.conn.execute(f'''ALTER TABLE {table} ADD CONSTRAINT reject_test_write
                    CHECK ({identifier} <> 'r2') NOT VALID''')
                self.conn.commit()
                before = self._state()
                try:
                    with patch.object(vectors, 'embed_texts',
                                      side_effect=lambda texts: [VECTOR[:] for _ in texts]):
                        with self.assertRaises(psycopg.errors.CheckViolation):
                            vectors.embed(self.conn)
                    self.assertEqual(self._state(), before)
                finally:
                    self.conn.rollback()
                    self.conn.execute(f'ALTER TABLE {table} DROP CONSTRAINT reject_test_write')
                    self.conn.commit()

    def test_import_sql_failures_roll_back_vector_and_metadata_batch(self):
        self._embed()
        path = self._export()
        self.conn.execute('TRUNCATE regulations.rag_chunk_embeddings, growpath_bge_meta.inputs')
        self.conn.commit()
        self._assert_import_write_failure_rolls_back_batch(path)

    def test_embedding_failure_preserves_existing_vectors_and_metadata(self):
        self._embed()
        self.conn.execute("UPDATE regulations.rag_chunks SET chunk_text=chunk_text || ' 변경'")
        self.conn.commit()
        before = self._state()
        with patch.object(vectors, 'embed_texts', side_effect=RuntimeError('mock model failure')):
            with self.assertRaisesRegex(RuntimeError, 'mock model failure'):
                vectors.embed(self.conn)
        self.assertEqual(self._state(), before)

    def _assert_source_guard_rolls_back_first_write(self, delete):
        self._embed()
        entries = [{'rag_chunk_id': row['rag_chunk_id'], 'input_sha256': vectors.input_hash(row),
                    'embedding': OTHER_VECTOR} for row in vectors.sources(self.conn)]
        if delete:
            self.conn.execute("DELETE FROM regulations.rag_chunks WHERE rag_chunk_id='r2'")
        else:
            self.conn.execute("UPDATE regulations.rag_chunks SET chunk_text='동시 변경' WHERE rag_chunk_id='r2'")
        self.conn.commit()
        before = self._state()
        with self.assertRaises(ValueError), self.conn.transaction():
            vectors.store_rows(self.conn, entries)
        self.assertEqual(self._state(), before)

    def test_store_rows_rejects_changed_source_and_rolls_back_first_write(self):
        self._assert_source_guard_rolls_back_first_write(delete=False)

    def test_store_rows_rejects_missing_source_and_rolls_back_first_write(self):
        self._assert_source_guard_rolls_back_first_write(delete=True)


if __name__ == '__main__':
    unittest.main()
