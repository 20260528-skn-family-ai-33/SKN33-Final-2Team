"""Reference-preservation regressions against an explicitly disposable PG clone."""
from datetime import datetime, timezone
import os
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.database.catalog_reset import delete_catalog_rows, replace_catalogs, TABLES
from src.database.catalog_verification import fingerprints
from src.database.ingestion.catalog_finalization import finalize_catalog
from src.shared.catalog_eligibility import eligible_keys


class CatalogHistoryDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ.get('EMPLOYEE_FORM_TEST_DB_URL')
        if not cls.url:
            raise unittest.SkipTest('Run scripts/check_workspace.py --integration')
        target = conninfo_to_dict(cls.url)
        if target.get('host') != '127.0.0.1' or not target.get('dbname', '').startswith('growpath_employee_form_test_'):
            raise RuntimeError('A disposable local clone is required')

    def setUp(self):
        self.conn = psycopg.connect(self.url, row_factory=dict_row)
        self.conn.execute('SELECT 1')

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def employee(self, job_id=None):
        return self.conn.execute('''INSERT INTO public.employees
            (name,email,employee_number,source_type,job_id)
            VALUES ('PR22 검증 직원',%s,%s,'TEST_MANUAL',%s) RETURNING employee_id''',
            (uuid4().hex+'@growpath.example.invalid', 'PR22-'+uuid4().hex, job_id)).fetchone()['employee_id']

    def copy_catalog(self, kind):
        pk, _ = TABLES[kind]
        row = self.conn.execute(f'SELECT to_jsonb(t) AS record FROM public.{kind} t ORDER BY {pk} LIMIT 1').fetchone()['record']
        row[pk] = self.conn.execute(f'SELECT coalesce(max({pk}),0)+1000 AS id FROM public.{kind}').fetchone()['id']
        row['title'] = 'PR22 검증 ' + kind + ' ' + uuid4().hex
        self.conn.execute(sql.SQL('INSERT INTO public.{} SELECT * FROM jsonb_populate_record(NULL::public.{},%s)').format(
            sql.Identifier(kind), sql.Identifier(kind)), (Jsonb(row),))
        return row[pk]

    def employee_references(self):
        job, cert, major = (self.copy_catalog(kind) for kind in ('jobs', 'certifications', 'majors'))
        employee = self.employee(job)
        self.conn.execute('INSERT INTO public.employee_certifications(employee_id,certification_id) VALUES (%s,%s)', (employee, cert))
        level = self.conn.execute('SELECT education_level FROM public.employee_education_records LIMIT 1').fetchone()['education_level']
        self.conn.execute('''INSERT INTO public.employee_education_records
            (employee_id,school_name,education_level,major_id) VALUES (%s,'PR22 검증 학교',%s,%s)''', (employee, level, major))
        return {'jobs': job, 'certifications': cert, 'majors': major}

    def hr_fingerprints(self):
        names = ('public.employees', 'public.employee_certifications', 'public.employee_education_records',
                 'public.employee_input_profiles')
        return {k: v for k, v in fingerprints(self.conn).items() if k in names}

    def test_reset_preserves_employee_references_and_external_identity(self):
        ids = self.employee_references()
        unreferenced = self.copy_catalog('jobs')
        key = 'pr22-'+uuid4().hex
        self.conn.execute('''INSERT INTO growpath_meta.catalog_api_sources
            (resource_type,source,external_key,entity_key,payload,mapping_evidence,fetched_at)
            VALUES ('jobs','PR22_TEST',%s,%s,'{"original":true}','{}',now())''', (key, str(ids['jobs'])))
        before = self.hr_fingerprints()
        result = delete_catalog_rows(self.conn)
        self.assertTrue(result['employee_references_preserved'])
        self.assertEqual(before, self.hr_fingerprints())
        for kind, rid in ids.items():
            pk, _ = TABLES[kind]
            self.assertEqual(self.conn.execute(f'SELECT content_status FROM public.{kind} WHERE {pk}=%s', (rid,)).fetchone()['content_status'], 'scope_excluded')
        self.assertIsNone(self.conn.execute('SELECT 1 FROM public.jobs WHERE job_id=%s', (unreferenced,)).fetchone())
        saved = self.conn.execute("SELECT entity_key,payload FROM growpath_meta.catalog_api_sources WHERE source='PR22_TEST' AND external_key=%s", (key,)).fetchone()
        self.assertEqual(saved, {'entity_key': str(ids['jobs']), 'payload': {'original': True}})
        self.assertTrue(all(n == 0 for n in delete_catalog_rows(self.conn)['deleted'].values()))
        self.assertEqual(before, self.hr_fingerprints())

    def test_excluded_only_reset_also_preserves_employee_references(self):
        ids = self.employee_references()
        for kind, rid in ids.items():
            pk, _ = TABLES[kind]
            self.conn.execute(f"UPDATE public.{kind} SET content_status='scope_excluded' WHERE {pk}=%s", (rid,))
        before = self.hr_fingerprints()
        delete_catalog_rows(self.conn, excluded_only=True)
        self.assertEqual(before, self.hr_fingerprints())
        for kind, rid in ids.items():
            self.assertIsNotNone(self.conn.execute(f'SELECT 1 FROM public.{kind} WHERE {TABLES[kind][0]}=%s', (rid,)).fetchone())

    def test_reset_failure_rolls_back_catalogs_and_references(self):
        self.employee_references()
        before = fingerprints(self.conn)
        with self.assertRaisesRegex(RuntimeError, 'simulated'):
            with self.conn.transaction():
                delete_catalog_rows(self.conn)
                raise RuntimeError('simulated downstream failure')
        self.assertEqual(before, fingerprints(self.conn))

    def test_reset_blocks_racing_employee_writes_until_transaction_ends(self):
        self.employee_references()
        delete_catalog_rows(self.conn)
        with psycopg.connect(self.url, row_factory=dict_row) as other:
            other.execute("SET lock_timeout='100ms'")
            with self.assertRaises(psycopg.errors.LockNotAvailable):
                with other.transaction():
                    other.execute('UPDATE public.employees SET name=name WHERE false')
            self.conn.rollback()
            other.execute('UPDATE public.employees SET name=name WHERE false')

    def test_replace_readmits_same_identity_without_losing_employee_links(self):
        ids = self.employee_references()
        skills = self.conn.execute('SELECT skill_id,name,category FROM public.skill_tags ORDER BY skill_id').fetchall()
        batch = {'skill_identity': skills, 'rows': {}}
        expected = set()
        for kind, (pk, _) in TABLES.items():
            rid = ids.get(kind)
            if rid is None:
                rid = self.conn.execute(f'SELECT {pk} FROM public.{kind} ORDER BY {pk} LIMIT 1').fetchone()[pk]
            fields = self.conn.execute(f'SELECT to_jsonb(t) AS record FROM public.{kind} t WHERE {pk}=%s', (rid,)).fetchone()['record']
            external = 'pr22-'+kind+'-'+uuid4().hex
            item = {'fields': fields, 'source': 'PR22_TEST', 'external_key': external,
                    'raw': {'refreshed': True}, 'matches': {1: ['SQL']}, 'fetched_at': datetime.now(timezone.utc)}
            batch['rows'][kind] = [item]
            expected.add((kind, str(rid)))
            if kind in ids:
                self.conn.execute('''INSERT INTO growpath_meta.catalog_api_sources
                    (resource_type,source,external_key,entity_key,payload,mapping_evidence,fetched_at)
                    VALUES (%s,'PR22_TEST',%s,%s,'{"old":true}','{}',now())''', (kind, external, str(rid)))
        before = self.hr_fingerprints()
        gate = MagicMock()
        gate.filter.side_effect = lambda kind, rows: rows
        # Only admission/evidence/embedding are mocked; reset/upsert/FKs are real PG.
        with patch('src.database.ingestion.ai_catalog_filter.AICatalogFilter', return_value=gate), \
             patch('src.database.catalog_reset.exclusion_reason', return_value=None), \
             patch('src.database.catalog_reset.scoped_matches', return_value={1: ['SQL']}), \
             patch('src.shared.catalog_eligibility.eligible_keys', return_value=(expected, {})), \
             patch('src.database.vectors.resource_vectors.status', return_value={}):
            for _ in range(2):
                self.assertEqual(replace_catalogs(self.conn, batch, embed=False)['status'], 'PASS')
                self.assertEqual(before, self.hr_fingerprints())
        for kind, rid in ids.items():
            self.assertEqual(self.conn.execute(f'SELECT content_status FROM public.{kind} WHERE {TABLES[kind][0]}=%s', (rid,)).fetchone()['content_status'], 'ready')
            self.assertEqual(self.conn.execute("SELECT payload FROM growpath_meta.catalog_api_sources WHERE resource_type=%s AND source='PR22_TEST' AND entity_key=%s", (kind, str(rid))).fetchone()['payload'], {'refreshed': True})

    def test_incremental_finalization_keeps_expired_and_rejected_roadmap_resources(self):
        allowed, _ = eligible_keys(self.conn)
        courses = sorted(rid for kind, rid in allowed if kind == 'courses')[:2]
        self.assertEqual(len(courses), 2)
        employee = self.employee()
        project = self.conn.execute("INSERT INTO public.projects(employee_id,project_name) VALUES (%s,'PR22 검증') RETURNING project_id", (employee,)).fetchone()['project_id']
        round_id = self.conn.execute("INSERT INTO public.diagnostic_rounds(project_id,round_number,project_snapshot) VALUES (%s,1,'{}') RETURNING diagnostic_round_id", (project,)).fetchone()['diagnostic_round_id']
        roadmap = self.conn.execute("INSERT INTO public.roadmaps(project_id,diagnostic_round_id,strategy_type,content,baseline_content) VALUES (%s,%s,'BALANCED','{}','{}') RETURNING roadmap_id", (project, round_id)).fetchone()['roadmap_id']
        step = self.conn.execute("INSERT INTO public.roadmap_steps(roadmap_id,step_order,title) VALUES (%s,1,'검증') RETURNING step_id", (roadmap,)).fetchone()['step_id']
        for rid in courses:
            self.conn.execute('INSERT INTO public.roadmap_step_resources(step_id,course_id) VALUES (%s,%s)', (step, rid))
        self.conn.execute("UPDATE growpath_meta.catalog_api_sources SET fetched_at=now()-interval '45 days' WHERE resource_type='courses' AND entity_key=%s", (courses[0],))
        self.conn.execute("UPDATE public.courses SET content_status='scope_excluded' WHERE course_id=%s", (courses[1],))
        before = self.hr_fingerprints()
        with patch('src.database.vectors.resource_vectors.embed', side_effect=AssertionError('No paid API in this test')):
            for _ in range(2):
                _, result = finalize_catalog(self.conn, embed=False)
                self.assertTrue(result['passed'])
                self.assertEqual(result['removed_rows']['removed_resource_associations'], 0)
                self.assertEqual(before, self.hr_fingerprints())
                self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM public.roadmap_step_resources WHERE step_id=%s', (step,)).fetchone()['n'], 2)
                for rid in courses:
                    self.assertEqual(self.conn.execute('SELECT content_status FROM public.courses WHERE course_id=%s', (rid,)).fetchone()['content_status'], 'scope_excluded')
                    self.assertIsNone(self.conn.execute("SELECT 1 FROM public.learning_resource_embeddings WHERE resource_type='courses' AND resource_id=%s", (rid,)).fetchone())
                current, _ = eligible_keys(self.conn)
                self.assertFalse(any(('courses', rid) in current for rid in courses))
