"""Real PostgreSQL writes/rollback; fake embeddings only, isolated clone required."""
import hashlib
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from src.database.vectors import resource_vectors as vectors


class ResourceRefreshDatabaseTests(unittest.TestCase):
    def setUp(self):
        url = os.environ.get('EMPLOYEE_FORM_TEST_DB_URL', '')
        if not url:
            self.skipTest('An isolated local test DB is required')
        params = conninfo_to_dict(url)
        if params.get('host') != '127.0.0.1' or not params.get('dbname', '').startswith('growpath_employee_form_test_'):
            raise ValueError('Refuse vector writes outside the isolated local test DB')
        self.c = psycopg.connect(url, row_factory=dict_row, connect_timeout=5)
        self.addCleanup(self.c.close)
        self.addCleanup(self.c.rollback)
        self.c.execute('SELECT 1')  # Outer transaction keeps all fixtures rollback-only.
        self.ids = [uuid4().hex[:13] for _ in range(3)]
        self.rows = {}
        for rid in self.ids:
            self.c.execute('INSERT INTO public.books(isbn,title) VALUES(%s,%s)', (rid, 'Vector regression fixture'))
            text = 'fixture-' + rid
            self.rows[('books', rid)] = {'hash': hashlib.sha256(text.encode()).hexdigest(), 'text': text, 'record': {}}
        self.fake = [1.0] + [0.0] * (vectors.DIMENSIONS - 1)
        self.api = self.enterContext(patch.object(vectors, 'embed_texts', side_effect=lambda texts, **kw: [self.fake for _ in texts]))
        self.enterContext(patch.object(vectors, 'sources', return_value=self.rows))

    def state(self):
        return self.c.execute('''SELECT resource_id,input_sha256,embedding::text,updated_at
            FROM public.learning_resource_embeddings WHERE resource_type='books'
            AND resource_id=ANY(%s) ORDER BY resource_id''', (self.ids,)).fetchall()

    def seed(self):
        vectors.embed(self.c, resource_types=['books'], max_records=3)
        self.api.reset_mock()

    def test_selected_update_preserves_unselected_and_noop_retry(self):
        self.seed()
        before = {r['resource_id']: r for r in self.state()}
        rid = self.ids[0]
        self.rows[('books', rid)]['hash'] = 'f' * 64
        result = vectors.embed(self.c, resource_types=['books'], resource_ids=[rid], max_records=1)
        self.assertEqual(result['embedded_count'], 1)
        after = {r['resource_id']: r for r in self.state()}
        self.assertEqual(after[rid]['input_sha256'], 'f' * 64)
        scores = vectors.similarities(self.c, self.rows, [('books', rid)], self.fake)
        self.assertAlmostEqual(scores[('books', rid)], 1.0)
        for other in self.ids[1:]:
            self.assertEqual(after[other], before[other])
        self.api.assert_called_once()
        self.api.reset_mock()
        retry = vectors.embed(self.c, resource_types=['books'], resource_ids=[rid], max_records=1)
        self.assertFalse(retry['database_changes'])
        self.assertEqual(self.state(), list(sorted(after.values(), key=lambda r: r['resource_id'])))
        self.api.assert_not_called()

    def test_api_failure_preserves_existing_vectors(self):
        self.seed()
        before = self.state()
        self.rows[('books', self.ids[0])]['hash'] = 'f' * 64
        self.api.side_effect = RuntimeError('simulated provider failure')
        with self.assertRaises(RuntimeError):
            vectors.embed(self.c, resource_types=['books'], max_records=1)
        self.assertEqual(self.state(), before)

    def test_foreign_key_failure_rolls_back_previous_writes(self):
        self.seed()
        before = self.state()
        for row in self.rows.values():
            row['hash'] = 'f' * 64
        # This ID sorts after all fixtures, so real upserts occur before the FK fails.
        self.rows[('books', 'zz-missing-fixture')] = {'hash': 'e' * 64, 'text': 'missing', 'record': {}}
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            vectors.embed(self.c, resource_types=['books'], max_records=4)
        self.assertEqual(self.state(), before)

    def test_concurrent_source_change_rolls_back_written_vectors(self):
        self.seed()
        before = self.state()
        self.rows[('books', self.ids[0])]['hash'] = 'f' * 64
        changed = {**self.rows, ('books', self.ids[0]): {'hash': 'e' * 64, 'text': 'changed', 'record': {}}}
        with patch.object(vectors, 'sources', side_effect=[self.rows, changed]):
            with self.assertRaisesRegex(ValueError, 'sources changed'):
                vectors.embed(self.c, resource_types=['books'], max_records=1)
        self.assertEqual(self.state(), before)

    def test_limit_failure_and_readonly_plan_write_nothing(self):
        before = self.state()
        with self.assertRaises(vectors.RefreshPlanError):
            vectors.embed(self.c, resource_types=['books'], max_records=2)
        result = vectors.plan(self.c, resource_types=['books'], max_records=3)
        self.assertEqual(result['pending_count'], 3)
        self.assertFalse(result['database_changes'])
        self.assertEqual(self.state(), before)
        self.api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
