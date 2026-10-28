"""Authenticated HTTP + real PostgreSQL contracts; isolated clone, no model calls."""
import copy
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import secrets
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict


class AppContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ.get('EMPLOYEE_FORM_TEST_DB_URL', '')
        if not url:
            raise unittest.SkipTest('An isolated local test DB is required')
        p = conninfo_to_dict(url)
        if p.get('host') != '127.0.0.1' or not p.get('dbname', '').startswith('growpath_employee_form_test_'):
            raise ValueError('Refuse HTTP fixtures outside the isolated local test DB')
        from sqlalchemy.engine import URL
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        cls.env = patch.dict(os.environ, {'DATABASE_URL': URL.create('postgresql+psycopg',
            username=p['user'], password=p.get('password'), host=p['host'], port=int(p.get('port', 5432)),
            database=p['dbname'], query={'connect_timeout': '5'}).render_as_string(hide_password=False)})
        cls.env.start()
        cls.addClassCleanup(cls.env.stop)
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
        from app import auth, db, errors, llm
        from app.routers import account, team, work
        from app.services import goals, plans, profile
        if (db.engine.url.host, db.engine.url.database, db.engine.url.port) != (p['host'], p['dbname'], int(p.get('port', 5432))):
            raise ValueError('The cached app engine does not point at the owned test clone')
        cls.db, cls.plans, cls.profile = db, plans, profile
        cls.addClassCleanup(db.engine.dispose)
        cls.enterClassContext(patch.object(llm, '_http', side_effect=AssertionError('External model calls forbidden in DB contracts')))
        cls.enterClassContext(patch.object(goals, 'request', return_value=None))  # Generation is evaluated separately.
        api = FastAPI()
        api.add_exception_handler(errors.ApiError, errors.api_error_handler)
        for router in (account.r, team.r, work.r):
            api.include_router(router)
        cls.api, cls.TestClient = api, TestClient
        cls.password = secrets.token_urlsafe(24)
        cls.password_hash = auth.hash_password(cls.password)

    def setUp(self):
        db = self.db
        self.inst = uuid4().hex
        self.foreign_inst = uuid4().hex
        self.ids, self.numbers = {}, {}
        with db.tx() as t:
            for inst in (self.inst, self.foreign_inst):
                t.run('INSERT INTO public.institutions(institution_id,name) VALUES(:i,:n)', i=inst, n='HTTP contract fixture')
            self.dept = t.val('INSERT INTO public.departments(institution_id,department_code,name) VALUES(:i,:c,:n) RETURNING department_id',
                i=self.inst, c=uuid4().hex, n='HTTP parent department')
            self.child = t.val('INSERT INTO public.departments(institution_id,department_code,name,parent_department_id) VALUES(:i,:c,:n,:p) RETURNING department_id',
                i=self.inst, c=uuid4().hex, n='HTTP child department', p=self.dept)
            for key, dept, head in (('head', self.dept, True), ('member', self.dept, False), ('peer', self.dept, False),
                                    ('child_head', self.child, True), ('child_member', self.child, False)):
                number = uuid4().hex
                self.numbers[key] = number
                self.ids[key] = t.val('''INSERT INTO public.employees(name,employee_number,source_type,institution_id,department_id,is_department_head,password_hash)
                    VALUES(:n,:c,'TEST_MANUAL',:i,:d,:h,:pw) RETURNING employee_id''',
                    n='HTTP fixture ' + key, c=number, i=self.inst, d=dept, h=head, pw=self.password_hash)
            self.project = str(t.val("INSERT INTO public.projects(employee_id,project_name,status) VALUES(:e,'HTTP fixture','IN_PROGRESS') RETURNING project_id", e=self.ids['member']))
            self.round = str(t.val('INSERT INTO public.diagnostic_rounds(project_id,round_number,project_snapshot) VALUES(CAST(:p AS uuid),1,:j) RETURNING diagnostic_round_id',
                p=self.project, j=db.J({})))
            self.plan = {'opt': 'balanced', 'name': 'Contract plan', 'tagline': 'Contract fixture', 'goal': 'Fixture goal',
                'version': 1, 'weeks': 2, 'hours': 2, 'prefs': {'hours': 2, 'weeks': 2, 'budget': 0, 'format': 'online', 'etc': 'fixture'},
                'def': {}, 'handoff': {'private': 'owner only'}, 'assess': {'questions': [], 'answers': {'private': 4}},
                'acts': [{'id': 'fixture-activity', 'title': 'Contract activity', 'stage': 1, 'hours': 2, 'wFrom': 1, 'wTo': 2,
                          'res': None, 'how': 'Practice', 'task': 'Output', 'skills': []}]}
            self.roadmap = self.plans.insert_roadmap(t, self.project, self.round, self.plan)
        self.clients = {}

    def client(self, role):
        if role not in self.clients:
            c = self.enterContext(self.TestClient(self.api))
            if role != 'anonymous':
                r = c.post('/api/v1/auth/login', json={'employeeNo': self.numbers[role], 'password': self.password})
                self.assertEqual(r.status_code, 200, r.text)
            self.clients[role] = c
        return self.clients[role]

    def get_plan(self, role='member'):
        r = self.client(role).get('/api/v1/plans/' + self.roadmap)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['plan']

    def test_auth_same_department_and_parent_department_scope(self):
        path = '/api/v1/team/plans/' + self.roadmap
        self.assertEqual(self.client('anonymous').get(path).status_code, 401)
        head = self.client('head').get(path)
        self.assertEqual(head.status_code, 200, head.text)
        self.assertNotIn('handoff', head.json()['plan']['plan'])
        self.assertEqual(head.json()['plan']['plan']['assess']['answers'], {})
        self.assertEqual(self.client('child_head').get(path).status_code, 404)
        self.assertEqual(self.client('peer').get(path).status_code, 403)
        self.assertEqual(self.client('head').get('/api/v1/team/members/' + str(self.ids['child_member']) + '/plans').status_code, 403)
        self.assertEqual(self.client('head').get('/api/v1/team/members/' + str(self.ids['child_head']) + '/plans').status_code, 403)
        members = self.client('head').get('/api/v1/team/members').json()['members']
        self.assertEqual({m['user']['id'] for m in members}, {str(self.ids['member']), str(self.ids['peer'])})
        self.assertNotIn('profile', members[0]['user'])
        self.assertEqual(self.client('head').get('/api/v1/plans/' + self.roadmap).status_code, 404)
        self.assertEqual(self.get_plan()['plan']['prefs'], self.plan['prefs'])

    def test_role_and_department_changes_revoke_existing_session(self):
        c = self.client('head')
        path = '/api/v1/team/plans/' + self.roadmap
        self.assertEqual(c.get(path).status_code, 200)
        with self.db.tx() as t:
            t.run('UPDATE public.employees SET is_department_head=false WHERE employee_id=:e', e=self.ids['head'])
        self.assertEqual(c.get(path).status_code, 403)
        with self.db.tx() as t:
            t.run('UPDATE public.employees SET is_department_head=true WHERE employee_id=:e', e=self.ids['head'])
            t.run('UPDATE public.employees SET department_id=:d WHERE employee_id=:e', d=self.child, e=self.ids['member'])
        self.assertEqual(c.get(path).status_code, 404)
        self.assertEqual(self.client('child_head').get(path).status_code, 200)

    def test_same_named_department_in_other_institution_is_not_shared(self):
        from sqlalchemy.exc import IntegrityError
        with self.assertRaises(IntegrityError), self.db.tx() as t:
            # Composite FK rejects an institution change that keeps the old department.
            t.run('UPDATE public.employees SET institution_id=:i WHERE employee_id=:e', i=self.foreign_inst, e=self.ids['member'])
        with self.db.tx() as t:
            foreign_dept = t.val('INSERT INTO public.departments(institution_id,department_code,name) VALUES(:i,:c,:n) RETURNING department_id',
                i=self.foreign_inst, c=uuid4().hex, n='HTTP parent department')
            t.run('UPDATE public.employees SET institution_id=:i,department_id=:d WHERE employee_id=:e',
                i=self.foreign_inst, d=foreign_dept, e=self.ids['member'])
            self.assertFalse(t.val('SELECT public.employee_can_read_employee(:a,:b)', a=self.ids['head'], b=self.ids['member']))
        self.assertEqual(self.client('head').get('/api/v1/team/plans/' + self.roadmap).status_code, 404)
        mine = self.client('member').get('/api/v1/me').json()['user']
        self.assertIsNone(mine['mySupervisor'])

    def test_personal_input_retry_revert_and_rejected_input_preserve_baseline(self):
        c = self.client('member')
        body = {'workDesc': 'Fixture work', 'expSummary': 'Fixture experience', 'devYears': 3.25,
                'tech': ['SQL fixture'], 'projects': ['Project fixture'], 'learning': ['Training fixture'], 'certs': ['Unlisted fixture'],
                'noneConfirmed': {}}
        before = self.db.one('SELECT * FROM public.employee_input_profiles WHERE employee_id=:e', e=self.ids['member'])
        for _ in range(2):
            r = c.put('/api/v1/me/profile/self', json=body)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(r.json()['self']['edited'])
        stored = self.db.one('SELECT * FROM public.employee_input_profiles WHERE employee_id=:e', e=self.ids['member'])
        self.assertEqual(stored['experience_summary'], body['expSummary'])
        self.assertEqual(float(stored['development_years']), 3.25)
        self.assertEqual(stored['technology_experience'], 'SQL fixture')
        self.assertEqual(self.db.val('SELECT unlisted_certifications FROM public.employees WHERE employee_id=:e', e=self.ids['member']), 'Unlisted fixture')
        for invalid in ({'expSummary': 'No work description'}, {'workDesc': 'Fixture', 'devYears': 51},
                        {'workDesc': 'Fixture', 'devYears': 'invalid'}, {'workDesc': 'Fixture', 'devYears': []}):
            self.assertEqual(c.put('/api/v1/me/profile/self', json=invalid).status_code, 422)
            self.assertEqual(self.db.one('SELECT * FROM public.employee_input_profiles WHERE employee_id=:e', e=self.ids['member']), stored)
        self.assertEqual(self.client('peer').get('/api/v1/plans/' + self.roadmap).status_code, 404)
        for _ in range(2):
            self.assertEqual(c.delete('/api/v1/me/profile/self').status_code, 200)
        self.assertEqual(self.db.one('SELECT * FROM public.employee_input_profiles WHERE employee_id=:e', e=self.ids['member']), before)
        self.assertIsNone(self.db.one('SELECT * FROM app_ext.employee_self_inputs WHERE employee_id=:e', e=self.ids['member']))

    def test_consent_grant_withdrawal_and_invalid_body(self):
        with self.db.tx() as t:
            t.run("INSERT INTO app_ext.employee_evaluations(employee_id,period,consent_default) VALUES(:e,'fixture',false)", e=self.ids['member'])
        c = self.client('member')
        path = '/api/v1/me/evaluations/fixture/consent'
        self.assertEqual(c.put(path, json={'consent': True}).status_code, 200)
        self.assertTrue(self.db.val("SELECT consent FROM app_ext.employee_evaluations WHERE employee_id=:e AND period='fixture'", e=self.ids['member']))
        for invalid in ({}, {'consent': 'false'}, {'consent': None}, {'consent': 1}):
            with self.subTest(body=invalid):
                self.assertEqual(c.put(path, json=invalid).status_code, 422)
        self.assertTrue(self.db.val("SELECT consent FROM app_ext.employee_evaluations WHERE employee_id=:e AND period='fixture'", e=self.ids['member']))
        for _ in range(2):
            self.assertEqual(c.put(path, json={'consent': False}).status_code, 200)
        row = self.db.one("SELECT * FROM app_ext.employee_evaluations WHERE employee_id=:e AND period='fixture'", e=self.ids['member'])
        self.assertIsNone(row['consent'])  # Inherit false default, not an erased evaluation.
        self.assertIsNotNone(row['consent_changed_at'])
        self.assertEqual(self.client('peer').put(path, json={'consent': True}).status_code, 404)

    def test_database_work_description_reaches_model_self_override_and_revert(self):
        from app.agents.goals import goal_input
        from app.agents.diag import work_profile
        eid = self.ids['member']
        with self.db.tx() as t:
            t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e',
                  w='DB supplied work description', e=eid)
        c = self.client('member')
        v = c.get('/api/v1/me/profile').json()['view']
        self.assertEqual(v['profile']['workDesc'], 'DB supplied work description')
        self.assertFalse(v['edited'])
        self.assertEqual(goal_input(v)['profile']['workDescription'], 'DB supplied work description')
        self.assertEqual(work_profile(v)['workDescription'], 'DB supplied work description')
        response = c.put('/api/v1/me/profile/self', json={'workDesc': 'Personal override', 'devYears': 0})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['view']['profile']['workDesc'], 'Personal override')
        with self.db.tx() as t:
            t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e',
                  w='Updated DB work description', e=eid)
        self.assertEqual(c.get('/api/v1/me/profile').json()['view']['profile']['workDesc'], 'Personal override')
        self.assertEqual(c.delete('/api/v1/me/profile/self').status_code, 200)
        v = c.get('/api/v1/me/profile').json()['view']
        self.assertEqual(v['profile']['workDesc'], 'Updated DB work description')
        self.assertFalse(v['edited'])
        self.assertNotIn('profile', self.profile.team_view(self.profile.view(eid)))

    def test_explicit_empty_work_override_and_legacy_missing_description(self):
        eid = self.ids['member']
        self.assertIsNone(self.profile.view(eid)['profile'])
        with self.db.tx() as t:
            t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e', w='DB default', e=eid)
            t.run('INSERT INTO app_ext.employee_self_inputs(employee_id,edited) VALUES(:e,:v)', e=eid, v=self.db.J({'workDesc': None}))
        self.assertIsNone(self.profile.view(eid)['profile'])
        with self.db.tx() as t:
            t.run('UPDATE app_ext.employee_self_inputs SET edited=:v WHERE employee_id=:e', e=eid, v=self.db.J({'inputStatus': {}}))
        self.assertEqual(self.profile.view(eid)['profile']['workDesc'], 'DB default')

    @staticmethod
    def self_body(view):
        """Use the same prefilled values as MePage's full personal-input save."""
        p = view.get('profile') or {}
        return {'workDesc': p.get('workDesc') or '', 'expSummary': p.get('expSummary') or '',
                'devYears': p.get('devYears'),
                **{k: list(view[k]) for k in ('tech', 'certs', 'learning', 'projects')},
                'noneConfirmed': {k: p.get('inputStatus', {}).get(k) == 'none_confirmed'
                                  for k in ('tech', 'certs', 'learning', 'projects')}}

    def test_unchanged_prefilled_self_save_preserves_original_rows(self):
        for role, with_profile in (('member', False), ('peer', True)):
            with self.subTest(with_profile=with_profile):
                eid = self.ids[role]
                with self.db.tx() as t:
                    t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e', w='DB work', e=eid)
                    t.run('INSERT INTO public.employee_skills(employee_id,skill_id) SELECT :e,skill_id FROM public.skill_tags ORDER BY skill_id LIMIT 1', e=eid)
                    if with_profile:
                        self.profile._write_profile(t, eid, {'experience_summary': 'Saved experience', 'development_years': 0,
                            'technology_experience': 'Saved technology', 'project_experience': 'Saved project', 'learning_history': 'Saved training'})
                before = self.db.one('SELECT * FROM public.employee_input_profiles WHERE employee_id=:e', e=eid)
                stamp = self.db.val('SELECT updated_at FROM public.employees WHERE employee_id=:e', e=eid)
                c = self.client(role)
                body = self.self_body(c.get('/api/v1/me/profile').json()['view'])
                for _ in range(2):
                    r = c.put('/api/v1/me/profile/self', json=body)
                    self.assertEqual(r.status_code, 200, r.text)
                    self.assertFalse(r.json()['self']['edited'])
                self.assertIsNone(self.db.one('SELECT * FROM app_ext.employee_self_inputs WHERE employee_id=:e', e=eid))
                self.assertEqual(self.db.one('SELECT * FROM public.employee_input_profiles WHERE employee_id=:e', e=eid), before)
                self.assertEqual(self.db.val('SELECT updated_at FROM public.employees WHERE employee_id=:e', e=eid), stamp)
                with self.db.tx() as t:
                    t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e', w='New DB work', e=eid)
                self.assertEqual(c.get('/api/v1/me/profile').json()['view']['profile']['workDesc'], 'New DB work')

    def test_technology_only_save_keeps_work_description_inherited_and_can_restore(self):
        eid = self.ids['member']
        with self.db.tx() as t:
            t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e', w='DB work', e=eid)
            t.run('INSERT INTO public.employee_skills(employee_id,skill_id) SELECT :e,skill_id FROM public.skill_tags ORDER BY skill_id LIMIT 1', e=eid)
        c = self.client('member')
        original = self.self_body(c.get('/api/v1/me/profile').json()['view'])
        body = dict(original, tech=original['tech'] + ['Added technology'])
        for _ in range(2):
            r = c.put('/api/v1/me/profile/self', json=body)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(r.json()['self']['edited'])
            self.assertNotIn('workDesc', self.db.val('SELECT edited FROM app_ext.employee_self_inputs WHERE employee_id=:e', e=eid))
        with self.db.tx() as t:
            t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e', w='New DB work', e=eid)
        v = c.get('/api/v1/me/profile').json()['view']
        self.assertEqual(v['profile']['workDesc'], 'New DB work')
        self.assertIn('Added technology', v['tech'])
        body = self.self_body(v)
        body['tech'] = original['tech']
        r = c.put('/api/v1/me/profile/self', json=body)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()['self']['edited'])
        self.assertIsNone(self.db.one('SELECT * FROM public.employee_input_profiles WHERE employee_id=:e', e=eid))

    def test_description_only_override_and_equal_db_value_do_not_copy_team_fields(self):
        eid = self.ids['member']
        with self.db.tx() as t:
            t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e', w='DB work', e=eid)
        c = self.client('member')
        body = self.self_body(c.get('/api/v1/me/profile').json()['view'])
        body['workDesc'] = 'Personal work'
        r = c.put('/api/v1/me/profile/self', json=body)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()['self']['edited'])
        self.assertIsNone(self.db.one('SELECT * FROM public.employee_input_profiles WHERE employee_id=:e', e=eid))
        with self.db.tx() as t:
            t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e', w='Personal work', e=eid)
        r = c.put('/api/v1/me/profile/self', json=body)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()['self']['edited'])
        with self.db.tx() as t:
            t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e', w='Later DB work', e=eid)
        self.assertEqual(c.get('/api/v1/me/profile').json()['view']['profile']['workDesc'], 'Later DB work')

    def test_certificate_only_retry_preserves_edited_links_and_can_restore(self):
        eid = self.ids['member']
        certs = self.db.all_('SELECT cert_id,title FROM public.certifications ORDER BY cert_id LIMIT 2')
        self.assertEqual(len(certs), 2)
        with self.db.tx() as t:
            t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e', w='DB work', e=eid)
            t.run('INSERT INTO public.employee_certifications(employee_id,certification_id) VALUES(:e,:c)', e=eid, c=certs[0]['cert_id'])
        c = self.client('member')
        original = self.self_body(c.get('/api/v1/me/profile').json()['view'])
        body = dict(original, certs=[x['title'] for x in certs])
        for _ in range(2):
            r = c.put('/api/v1/me/profile/self', json=body)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(r.json()['self']['edited'])
            self.assertEqual(set(r.json()['self']['certs']), {x['title'] for x in certs})
            self.assertNotIn('workDesc', self.db.val('SELECT edited FROM app_ext.employee_self_inputs WHERE employee_id=:e', e=eid))
        r = c.put('/api/v1/me/profile/self', json=original)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()['self']['edited'])
        self.assertEqual(r.json()['self']['certs'], [certs[0]['title']])

    def test_none_confirmed_is_preserved_without_work_description_override(self):
        eid = self.ids['member']
        with self.db.tx() as t:
            t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e', w='DB work', e=eid)
        c = self.client('member')
        body = self.self_body(c.get('/api/v1/me/profile').json()['view'])
        body['noneConfirmed']['learning'] = True
        r = c.put('/api/v1/me/profile/self', json=body)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()['self']['edited'])
        self.assertEqual(r.json()['self']['profile']['inputStatus']['learning'], 'none_confirmed')
        self.assertNotIn('workDesc', self.db.val('SELECT edited FROM app_ext.employee_self_inputs WHERE employee_id=:e', e=eid))

    def test_progress_retry_owner_only_and_manager_redaction(self):
        path = '/api/v1/plans/' + self.roadmap + '/activities/fixture-activity/progress'
        body = {'status': 'done', 'memo': 'Private memo', 'file': {'name': 'fixture.txt', 'size': 12}}
        self.assertEqual(self.client('head').put(path, json=body).status_code, 404)
        for _ in range(2):
            r = self.client('member').put(path, json=body)
            self.assertEqual(r.status_code, 200, r.text)
        row = self.db.one('SELECT * FROM app_ext.activity_progress WHERE roadmap_id=CAST(:r AS uuid)', r=self.roadmap)
        self.assertEqual((row['status'], row['memo'], row['attachment']), ('done', body['memo'], body['file']))
        self.assertEqual(self.db.val('SELECT count(*) FROM app_ext.activity_progress WHERE roadmap_id=CAST(:r AS uuid)', r=self.roadmap), 1)
        self.assertTrue(self.db.val('SELECT is_completed FROM public.roadmap_steps WHERE roadmap_id=CAST(:r AS uuid)', r=self.roadmap))
        manager = self.client('head').get('/api/v1/team/plans/' + self.roadmap).json()['plan']['progress']['fixture-activity']
        self.assertEqual(manager['status'], 'done')
        self.assertNotIn('memo', manager)
        self.assertNotIn('file', manager)
        self.assertEqual(self.client('member').put(path.replace('fixture-activity', 'missing'), json=body).status_code, 404)
        self.assertEqual(self.db.one('SELECT * FROM app_ext.activity_progress WHERE roadmap_id=CAST(:r AS uuid)', r=self.roadmap), row)

    def test_learning_preferences_persist_in_draft_and_remain_owner_only(self):
        c = self.client('member')
        prefs = {'hours': '4', 'weeks': '8', 'budget': '50000', 'format': 'online', 'cert': '', 'etc': 'After work'}
        made = c.post('/api/v1/drafts', json={'draft': {'goal': 'Preference fixture', 'prefs': prefs}})
        self.assertEqual(made.status_code, 200, made.text)
        draft_id = made.json()['draftId']
        updated = dict(prefs, hours='6', weeks='12')
        for _ in range(2):
            r = c.patch('/api/v1/drafts/' + draft_id, json={'prefs': updated})
            self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(c.get('/api/v1/drafts/current').json()['draft']['prefs'], updated)
        persisted = self.db.val('SELECT draft_choices FROM public.projects WHERE project_id=CAST(:p AS uuid)', p=draft_id)
        self.assertEqual(persisted['draft']['prefs'], updated)
        self.assertEqual(self.client('head').patch('/api/v1/drafts/' + draft_id, json={'prefs': prefs}).status_code, 404)
        self.assertEqual(self.db.val('SELECT draft_choices FROM public.projects WHERE project_id=CAST(:p AS uuid)', p=draft_id), persisted)

    def comment(self, text):
        from app.agents.demo import D
        body = {'fit': D['commentFit'][0][0], 'level': D['commentLevel'][0][0], 'free': text}
        r = self.client('head').post('/api/v1/team/plans/' + self.roadmap + '/comments', json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['commentId'], body

    def test_selected_comment_applies_to_one_version_and_preserves_baseline(self):
        selected, body = self.comment('Selected comment')
        other, _ = self.comment('Unselected comment')
        c = self.client('member')
        for _ in range(2):
            r = c.post('/api/v1/plans/' + self.roadmap + '/comments/' + selected + '/read')
            self.assertEqual(r.status_code, 200, r.text)
        before = self.get_plan()
        progress_path = '/api/v1/plans/' + self.roadmap + '/activities/fixture-activity/progress'
        self.assertEqual(c.put(progress_path, json={'status': 'done', 'memo': 'Preserve after revision'}).status_code, 200)
        progress = self.get_plan()['progress']
        revised = copy.deepcopy(self.plan)
        revised['name'] = 'Revised contract plan'
        revised['acts'][0]['title'] = 'Revised activity'
        pending = {'to': revised, 'from': self.plan, 'label': 'Selected comment applied', 'prefsTo': self.plan['prefs'],
                   'handoff': self.plan['handoff'], 'fromComment': selected}
        with self.db.tx() as t:
            revision = str(t.val("""INSERT INTO app_ext.roadmap_revisions(roadmap_id,request,result,status)
                VALUES(CAST(:r AS uuid),:q,:p,'ready') RETURNING revision_id""", r=self.roadmap, q=self.db.J({}), p=self.db.J(pending)))
        # Simulate a retry arriving while the first acceptance is still running.
        with self.TestClient(self.api) as retry_client:
            retry_client.cookies.update(c.cookies)
            with ThreadPoolExecutor(max_workers=2) as pool:
                requests = [pool.submit(client.post, '/api/v1/revisions/' + revision + '/accept') for client in (c, retry_client)]
                responses = [request.result(timeout=30) for request in requests]
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409], [r.text for r in responses])
        response = next(r for r in responses if r.status_code == 200)
        self.assertEqual(response.json()['version'], 2)
        self.assertEqual(c.post('/api/v1/revisions/' + revision + '/accept').status_code, 409)
        after = self.get_plan()
        self.assertEqual([v['version'] for v in after['versions']], [1, 2])
        self.assertEqual(after['versions'][0], before['versions'][0])
        self.assertEqual(after['progress'], progress)
        self.assertTrue(self.db.val('SELECT is_completed FROM public.roadmap_steps WHERE roadmap_id=CAST(:r AS uuid)', r=self.roadmap))
        self.assertEqual(self.db.val('SELECT baseline_content FROM public.roadmaps WHERE roadmap_id=CAST(:r AS uuid)', r=self.roadmap), self.plan)
        comments = {x['id']: x for x in after['comments']}
        self.assertEqual((comments[selected]['status'], comments[selected]['appliedVersion']), ('applied', 2))
        self.assertEqual((comments[other]['status'], comments[other]['appliedVersion']), ('new', None))
        edited = self.client('head').patch('/api/v1/team/plans/' + self.roadmap + '/comments/' + selected, json=dict(body, free='Changed'))
        self.assertEqual(edited.status_code, 409)


if __name__ == '__main__':
    unittest.main()
