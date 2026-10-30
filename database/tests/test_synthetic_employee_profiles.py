"""Fictional scenarios must agree with tenure, role and resolvable masters."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import unittest

from src.database.synthetic_employee_profiles import DEPARTMENTS, ROLES, SKILL_NAMES, scenario, _validate_entry


class SyntheticScenarioTests(unittest.TestCase):
    def setUp(self):
        self.skills = {sid + 1000: name for sid, name in SKILL_NAMES.items()}
        self.jobs = {r['job']: i + 20 for i, r in enumerate(ROLES.values())}
        self.certs = {r['cert']: i + 40 for i, r in enumerate(ROLES.values()) if r['cert']}
        self.employee = {'source_type': 'TEST_MANUAL', 'department_code': 'DATA',
                         'hire_date': date(2016, 3, 1), 'is_department_head': False}
        self.today = date(2026, 10, 28)

    def make(self, ordinal=0):
        return scenario(self.employee, ordinal, self.skills, self.jobs, self.certs, as_of=self.today)

    def test_all_department_scenarios_have_distinct_work_and_explain_every_link(self):
        work = set()
        for code in DEPARTMENTS:
            self.employee['department_code'] = code
            for ordinal in range(20):
                item = self.make(ordinal)
                p = item['payload']
                work.add(p['employee']['planned_project_description'])
                self.assertTrue(item['synthetic'])
                self.assertIn('synthetic=true', p['profile']['submission_note'])
                self.assertLessEqual(Decimal(p['profile']['development_years']), Decimal('10.66'))
                for sid in p['skill_ids']:
                    self.assertIn(self.skills[sid], p['profile']['technology_experience'])
        self.assertEqual(len(work), 100)

    def test_recent_hire_has_no_advanced_skills_or_claimed_independent_projects(self):
        self.employee['hire_date'] = date(2026, 10, 1)
        p = self.make(2)['payload']
        self.assertLessEqual(Decimal(p['profile']['development_years']), Decimal('0.07'))
        self.assertEqual(len(p['skill_ids']), 2)
        self.assertEqual(p['certification_ids'], [])
        self.assertIn('독립 수행 이력 없음', p['profile']['project_experience'])

    def test_human_or_future_hire_or_missing_master_is_rejected(self):
        self.employee['source_type'] = 'REAL_USER'
        with self.assertRaises(ValueError): self.make()
        self.employee['source_type'] = 'TEST_MANUAL'
        self.employee['hire_date'] = self.today
        with self.assertRaises(ValueError): self.make()
        self.employee['hire_date'] = date(2016, 3, 1)
        self.skills = {}
        with self.assertRaises(ValueError): self.make()

    def test_manager_scenario_does_not_grant_extra_permissions(self):
        self.employee['is_department_head'] = True
        p = self.make()['payload']
        self.assertIn('같은 부서', p['employee']['planned_project_description'])
        self.assertNotIn('is_department_head', p['employee'])
        self.assertNotIn('department_id', p['employee'])

    def test_plan_cannot_edit_identity_human_preferences_or_clear_evidence(self):
        entry = {'employee_id': 1, 'before_sha256': '0' * 64, **self.make()}
        _validate_entry(entry)
        for section, field, value in [('employee', 'name', 'forbidden'), ('employee', 'password_hash', 'forbidden'),
                                     ('profile', 'learning_preferences', {}), ('profile', 'experience_summary', '')]:
            bad = deepcopy(entry)
            bad['payload'][section][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): _validate_entry(bad)

    def test_provenance_is_required(self):
        entry = {'employee_id': 1, 'before_sha256': '0' * 64, **self.make()}
        entry['payload']['profile']['submission_note'] = 'a human wrote this'
        with self.assertRaises(ValueError): _validate_entry(entry)
