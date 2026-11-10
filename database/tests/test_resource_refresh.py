"""Refresh selection, preflight limits and rollback guards without a DB or API."""
from contextlib import redirect_stdout
from io import StringIO
import hashlib
import json
import unittest
from unittest.mock import MagicMock, patch

from src.database.vectors import resource_vectors as vectors
from src.shared.bge_embeddings import ACCEPTED_PROTOCOLS, PROVENANCE, IndexedEmbedding

FP16, FP32 = ACCEPTED_PROTOCOLS
TEXT_SHA = hashlib.sha256('private source text'.encode('utf-8')).hexdigest()


def source(value):
    return {'hash': value, 'text': 'private source text', 'record': {}}


def current(value):
    return {'input_sha256': value, 'input_version': vectors.INPUT_VERSION,
            'dimensions': vectors.DIMENSIONS, 'meta_sha256': value, 'actual_input_sha256': TEXT_SHA,
            'model_revision': PROVENANCE['model_revision'], 'protocol': FP16, 'token_count': 3}


def indexed(vector):
    return IndexedEmbedding(vector, FP32, 11)


class ResourceRefreshTests(unittest.TestCase):
    def test_retained_course_refresh_requires_explicit_course_ids(self):
        conn = MagicMock()
        for kinds, ids in [(['books'], ['001']), (['courses'], []), (None, ['001'])]:
            with self.subTest(kinds=kinds, ids=ids), self.assertRaises(vectors.RefreshPlanError):
                vectors.embed(conn, resource_types=kinds, resource_ids=ids, include_stored_courses=True)
        conn.execute.assert_not_called()

    def test_retained_current_course_keeps_its_vector(self):
        rows = {('courses', 'old'): source('same')}
        previous = {('courses', 'old'): current('same')}
        with patch.object(vectors, 'sources', return_value=rows) as read, \
                patch.object(vectors, 'stored', return_value=previous), patch.object(vectors, 'status', return_value={}), \
                patch.object(vectors, 'embed_for_index') as model:
            result = vectors.embed(MagicMock(), resource_types=['courses'], resource_ids=['old'], include_stored_courses=True)
        self.assertEqual(result['embedded_count'], 0)
        self.assertEqual(read.call_args.kwargs['retained_course_ids'], ('old',))
        model.assert_not_called()

    def setUp(self):
        self.rows = {('books', str(i)): source(f'new-{i}') for i in range(25)}
        self.rows[('books', 'current')] = source('same')
        self.rows[('jobs', '1')] = source('job-new')
        self.previous = {k: current('old') for k in self.rows}
        self.previous[('books', 'current')] = current('same')
        self.conn = MagicMock()

    def test_plan_identifies_25_stale_books_without_api_or_writes(self):
        with patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'embed_for_index') as api:
            result = vectors.plan(self.conn, resource_types=['books'], max_records=25)
        self.assertEqual((result['selected_count'], result['current_count'], result['pending_count']), (26, 1, 25))
        self.assertEqual(result['batch_count'], 1)
        self.assertTrue(all(r['resource_type'] == 'books' and r['reason'] == 'stale' for r in result['pending']))
        self.assertNotIn('private source text', json.dumps(result))
        self.assertFalse(result['embedding_api_called'])
        self.conn.execute.assert_not_called()
        api.assert_not_called()

    def test_selected_embed_updates_only_the_25_stale_books(self):
        batch = [[1.0] + [0.0] * (vectors.DIMENSIONS - 1) for _ in range(25)]
        with patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'status', return_value={}), patch.object(vectors, 'embed_for_index', return_value=[indexed(v) for v in batch]) as api:
            result = vectors.embed(self.conn, client='mock-client', resource_types=['books'], max_records=25)
        self.assertEqual(result['embedded_count'], 25)
        self.assertTrue(result['embedding_api_called'])
        self.assertEqual(len(api.call_args.args[0]), 25)
        writes = [c for c in self.conn.execute.call_args_list if c.args[0].startswith(f'INSERT INTO {vectors.TABLE}')]
        self.assertEqual(len(writes), 25)
        self.assertEqual({c.args[1][1] for c in writes}, {str(i) for i in range(25)})
        self.assertTrue(all(c.args[1][0] == 'books' and c.args[1][5] == f'new-{c.args[1][1]}' for c in writes))
        meta_writes = [c for c in self.conn.execute.call_args_list if c.args[0].startswith(f'INSERT INTO {vectors.META_TABLE}')]
        self.assertEqual(len(meta_writes), 25)
        self.assertEqual({c.args[1][1] for c in meta_writes}, {str(i) for i in range(25)})
        self.assertTrue(all(c.args[1][0] == 'books' and c.args[1][2] == f'new-{c.args[1][1]}' for c in meta_writes))
        self.assertTrue(all(c.args[1][3] == TEXT_SHA for c in meta_writes))
        # 서버가 보고한 정밀도·토큰 수를 공백 단어 수로 추정하지 않고 그대로 기록한다.
        self.assertTrue(all(c.args[1][4:] == (FP32, PROVENANCE['model_revision'], 11) for c in meta_writes))

    def test_count_growth_aborts_before_ddl_and_paid_calls(self):
        for cap in (24, 0, -1):
            with self.subTest(cap=cap), patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'embed_for_index') as api:
                with self.assertRaises(vectors.RefreshPlanError):
                    vectors.embed(self.conn, resource_types=['books'], max_records=cap)
                api.assert_not_called()
                self.conn.execute.assert_not_called()

    def test_unknown_id_and_ambiguous_selection_fail_before_writes(self):
        for kinds, ids in [(['books'], ['absent']), (['books', 'jobs'], ['1']), (['unknown'], None)]:
            with self.subTest(kinds=kinds, ids=ids), patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'embed_for_index') as api:
                with self.assertRaises(vectors.RefreshPlanError):
                    vectors.embed(self.conn, resource_types=kinds, resource_ids=ids)
                api.assert_not_called()
                self.conn.execute.assert_not_called()

    def test_missing_vector_and_utf8_limit(self):
        rows = {('books', 'new'): source('new')}
        with patch.object(vectors, 'sources', return_value=rows), patch.object(vectors, 'stored', return_value={}):
            result = vectors.plan(self.conn, resource_types=['books'], resource_ids=['new'])
        self.assertEqual(result['pending'][0]['reason'], 'missing')
        rows[('books', 'new')]['text'] = '\uac00' * 2666 + 'ab'
        with patch.object(vectors, 'sources', return_value=rows), patch.object(vectors, 'stored', return_value={}):
            self.assertEqual(vectors.plan(self.conn, resource_types=['books'])['input_utf8_bytes'], 8000)
        rows[('books', 'new')]['text'] = '\uac00' * 2667
        with patch.object(vectors, 'sources', return_value=rows), patch.object(vectors, 'stored', return_value={}), patch.object(vectors, 'embed_for_index') as api:
            with self.assertRaisesRegex(vectors.RefreshPlanError, '8000 UTF-8'):
                vectors.embed(self.conn, resource_types=['books'])
            api.assert_not_called()
            self.conn.execute.assert_not_called()

    def test_current_explicit_target_does_not_reembed_or_write(self):
        with patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'status', return_value={}), patch.object(vectors, 'embed_for_index') as api:
            result = vectors.embed(self.conn, resource_types=['books'], resource_ids=['current'])
        self.assertEqual(result['embedded_count'], 0)
        self.assertFalse(result['database_changes'])
        self.assertFalse(result['embedding_api_called'])
        self.conn.execute.assert_not_called()
        api.assert_not_called()

    def test_source_change_propagates_failure_to_transaction_rollback(self):
        changed = {**self.rows, ('books', '0'): source('changed-during-call')}
        with patch.object(vectors, 'sources', side_effect=[self.rows, changed]), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'embed_for_index', return_value=[indexed([1.0] * vectors.DIMENSIONS)]), patch.object(vectors, 'status') as status:
            with self.assertRaisesRegex(ValueError, 'sources changed'):
                vectors.embed(self.conn, resource_types=['books'], resource_ids=['0'], max_records=1)
        self.assertIs(self.conn.transaction.return_value.__exit__.call_args.args[0], ValueError)
        status.assert_not_called()

    def test_api_failure_propagates_without_success_or_hash_only_update(self):
        with patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'embed_for_index', side_effect=RuntimeError('mock failure')), patch.object(vectors, 'status') as status:
            with self.assertRaises(RuntimeError):
                vectors.embed(self.conn, resource_types=['books'], resource_ids=['0'])
        self.assertFalse(any(c.args[0].startswith('INSERT') for c in self.conn.execute.call_args_list))
        self.assertIs(self.conn.transaction.return_value.__exit__.call_args.args[0], RuntimeError)
        status.assert_not_called()

    def test_cli_plan_starts_a_read_only_transaction(self):
        with patch.object(vectors, 'connect') as connect, patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'embed_for_index') as api, redirect_stdout(StringIO()) as output:
            connect.return_value.__enter__.return_value = self.conn
            vectors.main(['plan', '--resource-type', 'books', '--max-records', '25'])
        self.conn.execute.assert_called_once_with('SET TRANSACTION READ ONLY')
        self.assertEqual(json.loads(output.getvalue())['pending_count'], 25)
        api.assert_not_called()

    def test_cli_invalid_selection_fails_before_connect(self):
        for args in [['embed', '--resource-id', '0'], ['plan', '--max-records', '0'], ['status', '--resource-type', 'books']]:
            with self.subTest(args=args), patch.object(vectors, 'connect') as connect, patch('sys.stderr', StringIO()):
                with self.assertRaises(SystemExit):
                    vectors.main(args)
                connect.assert_not_called()


    def test_vector_without_valid_metadata_is_not_current(self):
        src = source('same')
        self.assertTrue(vectors.is_current(src, current('same')))
        self.assertTrue(vectors.is_current(src, dict(current('same'), protocol=FP32)))
        for changes in ({'meta_sha256': None}, {'meta_sha256': 'old'}, {'actual_input_sha256': 'old'},
                        {'model_revision': 'old'}, {'protocol': 'old'}, {'token_count': 0}, {'token_count': 8193}):
            with self.subTest(changes=changes):
                self.assertFalse(vectors.is_current(src, dict(current('same'), **changes)))

    def test_missing_metadata_table_is_refused_before_embedding_or_ddl(self):
        self.conn.execute.return_value.fetchone.return_value = {'id': None}
        with patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'embed_for_index') as api:
            for call in (vectors.plan, vectors.embed):
                with self.subTest(call=call.__name__), self.assertRaisesRegex(ValueError, 'Restore the shared BGE-M3 database'):
                    call(self.conn, resource_types=['books'])
        api.assert_not_called()
        self.assertTrue(all('to_regclass' in c.args[0] for c in self.conn.execute.call_args_list))
        self.assertNotIn('growpath_bge_meta', vectors.DDL)

    def test_truncated_input_separates_source_and_actual_sha_and_is_current(self):
        # 전체 원문(소개 10000자)과 축약된 실제 입력 텍스트
        full_json_hash = 'full_json_hash_value'
        truncated_text = 'shortened representation of long text'
        actual_sha = hashlib.sha256(truncated_text.encode('utf-8')).hexdigest()
        src = {'hash': full_json_hash, 'text': truncated_text, 'record': {}}

        # 1. source_sha와 actual_sha가 서로 다른 정상 기존 메타에 대해 is_current는 True
        stored_good = {
            'input_sha256': full_json_hash,
            'input_version': vectors.INPUT_VERSION,
            'dimensions': vectors.DIMENSIONS,
            'meta_sha256': full_json_hash,
            'actual_input_sha256': actual_sha,
            'model_revision': PROVENANCE['model_revision'],
            'protocol': FP16,
            'token_count': 3,
        }
        self.assertTrue(vectors.is_current(src, stored_good))

        # 2. actual_input_sha256가 다르면 False
        stored_bad_actual = dict(stored_good, actual_input_sha256='wrong_sha')
        self.assertFalse(vectors.is_current(src, stored_bad_actual))

        # 3. embed() 시 source_sha256에는 full_json_hash, actual_input_sha256에는 actual_sha가 기록됨
        rows = {('books', 'long1'): src}
        previous = {('books', 'long1'): current('old')}
        with patch.object(vectors, 'sources', return_value=rows), \
             patch.object(vectors, 'stored', return_value=previous), \
             patch.object(vectors, 'status', return_value={}), \
             patch.object(vectors, 'embed_for_index', return_value=[indexed([1.0] * vectors.DIMENSIONS)]):
            vectors.embed(self.conn, client='mock-client', resource_types=['books'])

        meta_writes = [c for c in self.conn.execute.call_args_list if c.args[0].startswith(f'INSERT INTO {vectors.META_TABLE}')]
        self.assertEqual(len(meta_writes), 1)
        self.assertEqual(meta_writes[0].args[1][2], full_json_hash)
        self.assertEqual(meta_writes[0].args[1][3], actual_sha)


if __name__ == '__main__':
    unittest.main()
