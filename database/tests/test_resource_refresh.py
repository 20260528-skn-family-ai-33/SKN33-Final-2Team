"""Refresh selection, preflight limits and rollback guards without a DB or API."""
from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import MagicMock, patch

from src.database.vectors import resource_vectors as vectors


def source(value):
    return {'hash': value, 'text': 'private source text', 'record': {}}


def current(value):
    return {'input_sha256': value, 'input_version': vectors.INPUT_VERSION,
            'dimensions': vectors.DIMENSIONS}


class ResourceRefreshTests(unittest.TestCase):
    def setUp(self):
        self.rows = {('books', str(i)): source(f'new-{i}') for i in range(25)}
        self.rows[('books', 'current')] = source('same')
        self.rows[('jobs', '1')] = source('job-new')
        self.previous = {k: current('old') for k in self.rows}
        self.previous[('books', 'current')] = current('same')
        self.conn = MagicMock()

    def test_plan_identifies_25_stale_books_without_api_or_writes(self):
        with patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'embed_texts') as api:
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
        with patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'status', return_value={}), patch.object(vectors, 'embed_texts', return_value=batch) as api:
            result = vectors.embed(self.conn, client='mock-client', resource_types=['books'], max_records=25)
        self.assertEqual(result['embedded_count'], 25)
        self.assertTrue(result['embedding_api_called'])
        self.assertEqual(len(api.call_args.args[0]), 25)
        writes = [c for c in self.conn.execute.call_args_list if c.args[0].startswith('INSERT')]
        self.assertEqual(len(writes), 25)
        self.assertEqual({c.args[1][1] for c in writes}, {str(i) for i in range(25)})
        self.assertTrue(all(c.args[1][0] == 'books' and c.args[1][5] == f'new-{c.args[1][1]}' for c in writes))

    def test_count_growth_aborts_before_ddl_and_paid_calls(self):
        for cap in (24, 0, -1):
            with self.subTest(cap=cap), patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'embed_texts') as api:
                with self.assertRaises(vectors.RefreshPlanError):
                    vectors.embed(self.conn, resource_types=['books'], max_records=cap)
                api.assert_not_called()
                self.conn.execute.assert_not_called()

    def test_unknown_id_and_ambiguous_selection_fail_before_writes(self):
        for kinds, ids in [(['books'], ['absent']), (['books', 'jobs'], ['1']), (['unknown'], None)]:
            with self.subTest(kinds=kinds, ids=ids), patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'embed_texts') as api:
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
        with patch.object(vectors, 'sources', return_value=rows), patch.object(vectors, 'stored', return_value={}), patch.object(vectors, 'embed_texts') as api:
            with self.assertRaisesRegex(vectors.RefreshPlanError, '8000 UTF-8'):
                vectors.embed(self.conn, resource_types=['books'])
            api.assert_not_called()
            self.conn.execute.assert_not_called()

    def test_current_explicit_target_does_not_reembed_or_write(self):
        with patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'status', return_value={}), patch.object(vectors, 'embed_texts') as api:
            result = vectors.embed(self.conn, resource_types=['books'], resource_ids=['current'])
        self.assertEqual(result['embedded_count'], 0)
        self.assertFalse(result['database_changes'])
        self.assertFalse(result['embedding_api_called'])
        self.conn.execute.assert_not_called()
        api.assert_not_called()

    def test_source_change_propagates_failure_to_transaction_rollback(self):
        changed = {**self.rows, ('books', '0'): source('changed-during-call')}
        with patch.object(vectors, 'sources', side_effect=[self.rows, changed]), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'embed_texts', return_value=[[1.0] * vectors.DIMENSIONS]), patch.object(vectors, 'status') as status:
            with self.assertRaisesRegex(ValueError, 'sources changed'):
                vectors.embed(self.conn, resource_types=['books'], resource_ids=['0'], max_records=1)
        self.assertIs(self.conn.transaction.return_value.__exit__.call_args.args[0], ValueError)
        status.assert_not_called()

    def test_api_failure_propagates_without_success_or_hash_only_update(self):
        with patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'embed_texts', side_effect=RuntimeError('mock failure')), patch.object(vectors, 'status') as status:
            with self.assertRaises(RuntimeError):
                vectors.embed(self.conn, resource_types=['books'], resource_ids=['0'])
        self.assertFalse(any(c.args[0].startswith('INSERT') for c in self.conn.execute.call_args_list))
        self.assertIs(self.conn.transaction.return_value.__exit__.call_args.args[0], RuntimeError)
        status.assert_not_called()

    def test_cli_plan_starts_a_read_only_transaction(self):
        with patch.object(vectors, 'connect') as connect, patch.object(vectors, 'sources', return_value=self.rows), patch.object(vectors, 'stored', return_value=self.previous), patch.object(vectors, 'embed_texts') as api, redirect_stdout(StringIO()) as output:
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


if __name__ == '__main__':
    unittest.main()
