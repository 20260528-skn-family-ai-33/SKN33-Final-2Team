"""Real final-snapshot contracts. Runner supplies only an isolated clone connection."""
import os
import unittest
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from src.database.db_client import DatabaseClient
from src.database.employee_form import get_employee_input_form,save_employee_input_form
from src.database.final_schema import verify


class FinalDatabaseTests(unittest.TestCase):
    def setUp(self):
        url=os.environ.get('EMPLOYEE_FORM_TEST_DB_URL')
        if not url:self.skipTest('Run scripts/check_workspace.py --integration')
        target=conninfo_to_dict(url)
        if target.get('host')!='127.0.0.1' or not target.get('dbname','').startswith('growpath_employee_form_test_'):
            raise RuntimeError('An isolated local clone is required')
        self.conn=psycopg.connect(url,row_factory=dict_row)
        self.conn.execute('SELECT 1')

    def tearDown(self):
        if hasattr(self,'conn'):
            self.conn.rollback();self.conn.close()

    def test_new_course_columns_are_available_through_existing_client(self):
        rows=DatabaseClient(self.conn).table('courses').select('course_id,enrollment_period_type,enrollment_start,enrollment_end,ai_mention').limit(3).execute().data
        self.assertTrue(rows)
        self.assertTrue(all('enrollment_period_type' in row for row in rows))

    def test_availability_view_keeps_all_courses_and_correct_unrestricted_state(self):
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM public.courses').fetchone()['n'],self.conn.execute('SELECT count(*) AS n FROM public.course_availability').fetchone()['n'])
        invalid=self.conn.execute("SELECT count(*) AS n FROM public.course_availability WHERE enrollment_period_type='unrestricted' AND (enrollment_status IS DISTINCT FROM 'ongoing' OR enrollment_start IS NOT NULL OR enrollment_end IS NOT NULL)").fetchone()['n']
        self.assertEqual(invalid,0)

    def test_profile_only_save_preserves_existing_missing_number(self):
        employee=self.conn.execute("SELECT employee_id FROM public.employees WHERE source_type='REAL_USER' AND employee_number IS NULL ORDER BY employee_id LIMIT 1").fetchone()
        if employee is None:self.skipTest('No incomplete legacy account remains')
        identity=employee['employee_id']
        saved=save_employee_input_form(self.conn,identity,{'profile':{'experience_summary':'검증 원문','development_years':0}})
        self.assertEqual(saved['profile']['experience_summary'],'검증 원문')
        self.assertIsNone(saved['employee']['employee_number'])

    def test_basic_profile_patch_requires_real_number_without_fabricating_one(self):
        employee=self.conn.execute("SELECT employee_id FROM public.employees WHERE source_type='REAL_USER' AND employee_number IS NULL ORDER BY employee_id LIMIT 1").fetchone()
        if employee is None:self.skipTest('No incomplete legacy account remains')
        identity=employee['employee_id']
        with self.assertRaisesRegex(ValueError,'실제 사번'):
            save_employee_input_form(self.conn,identity,{'employee':{'hire_date':'2020-01-01'}})
        self.assertIsNone(get_employee_input_form(self.conn,identity)['employee']['employee_number'])

    def test_number_can_be_supplied_with_basic_fields_atomically(self):
        employee=self.conn.execute("SELECT employee_id FROM public.employees WHERE source_type='REAL_USER' AND employee_number IS NULL ORDER BY employee_id LIMIT 1").fetchone()
        if employee is None:self.skipTest('No incomplete legacy account remains')
        number='ROLLBACK-'+str(uuid4())
        saved=save_employee_input_form(self.conn,employee['employee_id'],{'employee':{'employee_number':number,'hire_date':'2020-01-01'}})
        self.assertEqual(saved['employee']['employee_number'],number)

    def test_new_blank_employee_number_is_rejected_by_database(self):
        with self.assertRaises(psycopg.errors.CheckViolation),self.conn.transaction():
            self.conn.execute("INSERT INTO public.employees(name,employee_number,source_type) VALUES('검증용','  ','TEST_MANUAL')")

    def test_deferred_source_check_is_visible_and_unrelated_drift_still_fails(self):
        checked=verify(self.conn)
        self.assertEqual(checked['schema_and_foreign_keys'],'pass')
        self.assertTrue(any(r['constraint']=='employees_number_required' for r in checked['pending_constraints']))
        with self.conn.transaction(force_rollback=True):
            self.conn.execute('ALTER TABLE public.books ADD CONSTRAINT unexpected_review_check CHECK (true) NOT VALID')
            with self.assertRaisesRegex(ValueError,'Unexpected unvalidated'):
                verify(self.conn)

    def test_vector_operators_work_without_external_embedding_calls(self):
        for relation in ('public.learning_resource_embeddings','regulations.rag_chunk_embeddings'):
            row=self.conn.execute('SELECT embedding <=> embedding AS d FROM '+relation+' WHERE embedding IS NOT NULL LIMIT 1').fetchone()
            self.assertIsNotNone(row)
            self.assertAlmostEqual(row['d'],0,places=5)


if __name__=='__main__':unittest.main()
