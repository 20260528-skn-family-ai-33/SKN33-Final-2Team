"""Synthetic backfill on an explicitly supplied disposable PostgreSQL restore."""
from copy import deepcopy
from datetime import date
import os
import unittest

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from src.database.catalog_verification import fingerprints
from src.database.synthetic_employee_profiles import apply_plan, digest, plan, state


class SyntheticEmployeeDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value = os.environ.get('EMPLOYEE_FORM_TEST_DB_URL', '')
        if not value:
            raise unittest.SkipTest('An isolated local restored DB with 100 fictional employees is required')
        cls.params = conninfo_to_dict(value)
        if cls.params.get('host') != '127.0.0.1' or not cls.params.get('dbname', '').startswith('growpath_employee_form_test_'):
            raise ValueError('Refuse synthetic test writes outside an owned disposable restore')

    def setUp(self):
        self.c = psycopg.connect(**self.params, row_factory=dict_row)
        self.addCleanup(self.c.close)
        self.enterContext(self.c.transaction(force_rollback=True))
        # Restored post-correction snapshots use the same rollback-only fixtures.
        self.c.execute("DELETE FROM public.employee_input_profiles p USING public.employees e WHERE e.employee_id=p.employee_id AND e.source_type='TEST_MANUAL'")
        self.c.execute("UPDATE public.employee_education_records r SET major_id=NULL FROM public.employees e WHERE e.employee_id=r.employee_id AND e.source_type='TEST_MANUAL'")
        self.reviewed = plan(self.c, as_of=date(2026, 10, 28))

    def test_preview_never_changes_rows(self):
        before = fingerprints(self.c)
        self.assertEqual(apply_plan(self.c, self.reviewed)['changed_count'], 100)
        self.assertEqual(fingerprints(self.c), before)

    def test_apply_retry_preserves_five_humans_and_identity_password_permissions(self):
        real = self.c.execute("SELECT employee_id FROM public.employees WHERE source_type='REAL_USER'").fetchall()
        before = {r['employee_id']: digest(state(self.c, r['employee_id'])) for r in real}
        identities = digest(self.c.execute("SELECT employee_id,password_hash,employee_number,name,department_id,institution_id,is_department_head FROM public.employees ORDER BY employee_id").fetchall())
        result = apply_plan(self.c, self.reviewed, apply=True)
        self.assertEqual(result['changed_count'], 100)
        self.assertEqual(apply_plan(self.c, self.reviewed, apply=True)['changed_count'], 0)
        self.assertEqual({r['employee_id']: digest(state(self.c, r['employee_id'])) for r in real}, before)
        self.assertEqual(digest(self.c.execute("SELECT employee_id,password_hash,employee_number,name,department_id,institution_id,is_department_head FROM public.employees ORDER BY employee_id").fetchall()), identities)

    def test_real_user_or_duplicate_or_missing_target_rejected_before_write(self):
        before = fingerprints(self.c)
        human = self.c.execute("SELECT employee_id FROM public.employees WHERE source_type='REAL_USER' LIMIT 1").fetchone()['employee_id']
        bad = deepcopy(self.reviewed)
        bad['entries'][0]['employee_id'] = human
        with self.assertRaises(ValueError): apply_plan(self.c, bad, apply=True)
        bad = deepcopy(self.reviewed)
        bad['entries'][0]['employee_id'] = bad['entries'][1]['employee_id']
        with self.assertRaises(ValueError): apply_plan(self.c, bad, apply=True)
        self.assertEqual(fingerprints(self.c), before)

    def test_concurrent_edit_is_preserved_and_stale_plan_rejected(self):
        eid = self.reviewed['entries'][0]['employee_id']
        self.c.execute('UPDATE public.employees SET planned_project_description=%s WHERE employee_id=%s', ('A newer submitted value', eid))
        before = fingerprints(self.c)
        with self.assertRaisesRegex(ValueError, 'changed after plan'): apply_plan(self.c, self.reviewed, apply=True)
        self.assertEqual(fingerprints(self.c), before)

    def test_late_fk_failure_rolls_back_earlier_employee_writes(self):
        bad = deepcopy(self.reviewed)
        bad['entries'][-1]['payload']['skill_ids'].append(2147483647)
        before = fingerprints(self.c)
        with self.assertRaises(psycopg.errors.ForeignKeyViolation): apply_plan(self.c, bad, apply=True)
        self.assertEqual(fingerprints(self.c), before)

    def test_education_cannot_link_another_employee_record(self):
        bad = deepcopy(self.reviewed)
        source = next(x for x in bad['entries'] if 'education' in x['payload'])
        other = next(x for x in bad['entries'] if x['employee_id'] != source['employee_id'])
        other['payload']['education'] = source['payload']['education']
        before = fingerprints(self.c)
        with self.assertRaisesRegex(ValueError, 'Education link'): apply_plan(self.c, bad, apply=True)
        self.assertEqual(fingerprints(self.c), before)
