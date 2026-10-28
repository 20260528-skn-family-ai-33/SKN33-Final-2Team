"""Same-department permissions on an explicitly selected disposable PostgreSQL DB."""
import os
from pathlib import Path
import unittest
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from src.database.db_client import DatabaseClient, DatabaseOperationError


class DepartmentAccessTests(unittest.TestCase):
    def setUp(self):
        url = os.environ.get('EMPLOYEE_FORM_TEST_DB_URL', '')
        if not url:
            self.skipTest('An isolated local test DB is required')
        params = conninfo_to_dict(url)
        if params.get('host') != '127.0.0.1' or not params.get('dbname', '').startswith('growpath_employee_form_test_'):
            raise ValueError('Refuse fixtures outside the isolated local test DB')
        self.c = psycopg.connect(url, row_factory=dict_row)
        self.addCleanup(self.c.close)
        self.addCleanup(self.c.rollback)
        self.c.execute('SELECT 1')
        self.db = DatabaseClient(self.c)
        self.inst = uuid4().hex
        self.foreign_inst = uuid4().hex
        for inst in (self.inst, self.foreign_inst):
            self.c.execute('INSERT INTO public.institutions(institution_id,name) VALUES(%s,%s)', (inst, '권한 검증 기관'))

        def department(parent=None, inst=None):
            return self.c.execute('INSERT INTO public.departments(institution_id,department_code,name,parent_department_id) VALUES(%s,%s,%s,%s) RETURNING department_id',
                (inst or self.inst, uuid4().hex, '권한 검증 부서', parent)).fetchone()['department_id']

        self.root = department()
        self.child = department(self.root)
        self.team = department(self.child)
        self.sibling = department(self.root)
        foreign = department(inst=self.foreign_inst)

        def employee(dept, head=False, inst=None):
            return self.c.execute('INSERT INTO public.employees(name,employee_number,source_type,institution_id,department_id,is_department_head) VALUES(%s,%s,%s,%s,%s,%s) RETURNING employee_id',
                ('권한 검증 직원', uuid4().hex, 'TEST_MANUAL', inst or self.inst, dept, head)).fetchone()['employee_id']

        self.ids = {'hq': employee(self.root, True), 'hq_staff': employee(self.root),
                    'child': employee(self.child, True), 'child_staff': employee(self.child),
                    'team': employee(self.team, True), 'team_staff': employee(self.team),
                    'sibling': employee(self.sibling, True), 'sibling_staff': employee(self.sibling),
                    'foreign': employee(foreign, True, self.foreign_inst), 'unassigned': employee(None)}
        self.visible = {'hq': {'hq', 'hq_staff'},
                        'child': {'child', 'child_staff'},
                        'team': {'team', 'team_staff'}, 'sibling': {'sibling', 'sibling_staff'}}
        for name in self.ids:
            self.visible.setdefault(name, {name})
        self.projects = {name: self.db.create_roadmap_session(eid, '권한 검증') for name, eid in self.ids.items()}

    def allowed(self, actor, target):
        return self.c.execute('SELECT public.employee_can_read_employee(%s,%s) AS allowed', (actor, target)).fetchone()['allowed']

    def test_employee_and_project_access_matrix(self):
        for actor_name, actor in self.ids.items():
            for target_name, target in self.ids.items():
                with self.subTest(actor=actor_name, target=target_name):
                    expected = target_name in self.visible[actor_name]
                    self.assertEqual(self.allowed(actor, target), expected)
                    actual = self.c.execute('SELECT public.employee_can_read_project(%s,%s) AS allowed', (actor, self.projects[target_name])).fetchone()['allowed']
                    self.assertEqual(actual, expected)

    def test_profile_api_lists_and_reads_only_same_department(self):
        for name, actor in self.ids.items():
            visible = self.db.list_visible_employee_profiles(actor_employee_id=actor)
            self.assertEqual({row['employee_id'] for row in visible}, {self.ids[n] for n in self.visible[name]})
            for target_name, target in self.ids.items():
                if target_name in self.visible[name]:
                    self.assertNotIn('password_hash', self.db.get_employee_profile(target, actor_employee_id=actor))
                else:
                    with self.assertRaises(ValueError):
                        self.db.get_employee_profile(target, actor_employee_id=actor)

    def test_null_missing_ids_and_unassigned_self(self):
        for actor, target in ((None, self.ids['team_staff']), (self.ids['hq'], None),
                              (2147483647, self.ids['team_staff']), (self.ids['hq'], 2147483647)):
            self.assertFalse(self.allowed(actor, target))
        self.assertFalse(self.c.execute('SELECT public.employee_can_read_project(%s,%s) AS allowed', (self.ids['hq'], uuid4())).fetchone()['allowed'])
        self.assertTrue(self.allowed(self.ids['unassigned'], self.ids['unassigned']))
        self.assertFalse(self.allowed(self.ids['hq'], self.ids['unassigned']))

    def test_role_and_assignment_changes_revoke_access_immediately(self):
        self.assertTrue(self.allowed(self.ids['team'], self.ids['team_staff']))
        self.c.execute('UPDATE public.employees SET is_department_head=false WHERE employee_id=%s', (self.ids['team'],))
        self.assertFalse(self.allowed(self.ids['team'], self.ids['team_staff']))
        self.assertFalse(self.allowed(self.ids['child'], self.ids['team']))
        self.c.execute('UPDATE public.employees SET is_department_head=true WHERE employee_id=%s', (self.ids['team'],))
        self.c.execute('UPDATE public.employees SET department_id=%s WHERE employee_id=%s', (self.sibling, self.ids['team_staff']))
        self.assertFalse(self.allowed(self.ids['team'], self.ids['team_staff']))
        self.assertTrue(self.allowed(self.ids['sibling'], self.ids['team_staff']))

    def roadmap(self, name):
        pid = self.projects[name]
        content = {'milestones': [{'phase_name': '검증', 'duration': '1주', 'key_actions': ['검증']}]}
        self.db.save_roadmap_generations(pid, [{'strategy_type': 'BALANCED', 'strategy_title': '검증', 'roadmap_content': content}])
        rid = self.db.get_roadmap_generations(pid)[0]['generation_id']
        self.db.select_roadmap_with_report(pid, rid, {'title': '검증'})
        return rid

    def test_comments_and_progress_follow_same_department_but_writes_stay_owner_only(self):
        child_roadmap = self.roadmap('child')
        staff_roadmap = self.roadmap('team_staff')
        with self.assertRaises(DatabaseOperationError):
            self.db.add_roadmap_comment(self.ids['hq'], child_roadmap, '다른 부서장 검토는 차단')
        with self.assertRaises(ValueError):
            self.db.get_roadmap_progress(self.ids['hq'], child_roadmap)
        self.db.add_roadmap_comment(self.ids['team'], staff_roadmap, '팀원 검토')
        self.assertEqual(self.db.get_roadmap_progress(self.ids['team'], staff_roadmap)['completed_steps'], 0)
        with self.assertRaises(DatabaseOperationError):
            self.db.add_roadmap_comment(self.ids['hq'], staff_roadmap, '차단되어야 함')
        with self.assertRaises(ValueError):
            self.db.get_roadmap_progress(self.ids['child'], staff_roadmap)
        step = self.c.execute('SELECT step_id FROM public.roadmap_steps WHERE roadmap_id=%s', (staff_roadmap,)).fetchone()['step_id']
        with self.assertRaises(ValueError):
            self.db.set_step_completed(self.ids['team'], step, True)
        with self.assertRaises(ValueError):
            self.db.get_employee_input_form(self.ids['team_staff'], actor_employee_id=self.ids['team'])

    def test_permission_migration_is_repeatable_and_transactional(self):
        migration = Path(__file__).resolve().parents[1] / 'src/database/migrations/024_same_department_visibility.sql'
        self.c.execute(migration.read_text(encoding='utf-8'), prepare=False)
        self.assertFalse(self.allowed(self.ids['hq'], self.ids['team_staff']))
        old = migration.with_name('007_final_schema.sql').read_text(encoding='utf-8')
        old_function = old[old.index('CREATE FUNCTION public.employee_can_read_project('):old.index('CREATE FUNCTION public.guard_roadmap_comment(')]
        with self.c.transaction(force_rollback=True):
            self.c.execute(old_function.replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1), prepare=False)
            self.assertTrue(self.c.execute('SELECT public.employee_can_read_project(%s,%s) AS allowed', (self.ids['hq'], self.projects['team_staff'])).fetchone()['allowed'])
        self.assertFalse(self.c.execute('SELECT public.employee_can_read_project(%s,%s) AS allowed', (self.ids['hq'], self.projects['team_staff'])).fetchone()['allowed'])

    def test_upgrade_from_023_removes_child_head_access_and_ignores_hierarchy_changes(self):
        folder = Path(__file__).resolve().parents[1] / 'src/database/migrations'
        with self.c.transaction(force_rollback=True):
            self.c.execute((folder / '023_direct_department_visibility.sql').read_text(encoding='utf-8'), prepare=False)
            self.assertTrue(self.allowed(self.ids['hq'], self.ids['child']))
            migration = (folder / '024_same_department_visibility.sql').read_text(encoding='utf-8')
            self.c.execute(migration, prepare=False)
            self.c.execute(migration, prepare=False)
            self.assertFalse(self.allowed(self.ids['hq'], self.ids['child']))
            self.assertTrue(self.allowed(self.ids['child'], self.ids['child_staff']))
            self.c.execute('UPDATE public.departments SET parent_department_id=%s WHERE department_id=%s', (self.sibling, self.child))
            self.assertFalse(self.allowed(self.ids['hq'], self.ids['child']))
            self.assertFalse(self.allowed(self.ids['sibling'], self.ids['child']))
            self.assertTrue(self.allowed(self.ids['child'], self.ids['child_staff']))


if __name__ == '__main__':
    unittest.main()
