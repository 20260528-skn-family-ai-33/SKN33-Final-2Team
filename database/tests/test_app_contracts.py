"""Authenticated HTTP + real PostgreSQL contracts; isolated clone, no model calls."""
import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
import os
from pathlib import Path
import secrets
import subprocess
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
        cls.db, cls.plans, cls.profile, cls.goals = db, plans, profile, goals
        cls.actual_goal_request = staticmethod(goals.request)
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

    def duration_resource(self):
        from app import catalog
        rid='HTTP_DURATION_'+uuid4().hex
        with self.db.tx() as t:
            t.run("INSERT INTO public.courses(course_id,title,platform,content_status,estimated_duration_seconds) VALUES(:k,'시간 확인 검증','MS Learn','ready',3600)",k=rid)
            t.run("""INSERT INTO app_ext.resource_meta(resource_key,resource_type,course_id,hours,hours_origin,estimated_fields,stage)
                     VALUES(:k,'course',:c,1,'catalog',:e,1)""",k=rid,c=rid,e=self.db.J(['hours','stage']))
        def remove():
            with self.db.tx() as t:t.run('DELETE FROM public.courses WHERE course_id=:k',k=rid)
            catalog.invalidate()
        self.addCleanup(remove)
        catalog.invalidate()
        return rid

    def test_admin_can_confirm_time_without_changing_the_number_and_sync_preserves_it(self):
        from app import catalog,course_time
        from app.admin_io import base,education
        rid=self.duration_resource()
        cur={'강좌':{(rid,):education.current('강좌')[(rid,)]},'도서':{},'자격증':{}}
        row=base.Row('강좌',2,{'key':rid,'estimated':['단계']},{'key','estimated'},key=(rid,))
        base.diff(education.COURSE,[row],cur['강좌'],lambda value:education.label('강좌',value))
        self.assertEqual(row.action,'update')
        self.assertEqual([c['field'] for c in row.changes],['estimated'])
        with self.db.tx() as t:
            education.apply(t,{'강좌':[row]},cur,{})
            self.assertEqual(t.val('SELECT hours_origin FROM app_ext.resource_meta WHERE resource_key=:k',k=rid),'manual')
            t.run('UPDATE public.courses SET estimated_duration_seconds=7200 WHERE course_id=:k',k=rid)
            course_time.sync(t)
        catalog.invalidate()
        response=self.client('member').get('/api/v1/resources/'+rid)
        self.assertEqual(response.status_code,200,response.text)
        r=response.json()
        self.assertEqual((r['hours'],r['timeStatus']),(1,'manual'))
        self.assertNotIn('hours',r['estimated'])
        self.assertIn('stage',r['estimated'])

    def test_admin_unrelated_change_does_not_confirm_an_estimated_time(self):
        from app import catalog
        from app.admin_io import base,education
        rid=self.duration_resource()
        cur={'강좌':{(rid,):education.current('강좌')[(rid,)]},'도서':{},'자격증':{}}
        row=base.Row('강좌',2,{'key':rid,'note':'시간 확인과 무관한 메모'},{'key','note'},key=(rid,))
        base.diff(education.COURSE,[row],cur['강좌'],lambda value:education.label('강좌',value))
        with self.db.tx() as t:
            education.apply(t,{'강좌':[row]},cur,{})
            self.assertEqual(t.val('SELECT hours_origin FROM app_ext.resource_meta WHERE resource_key=:k',k=rid),'catalog')
        catalog.invalidate()
        r=self.client('member').get('/api/v1/resources/'+rid).json()
        self.assertEqual(r['timeStatus'],'estimated')
        self.assertIn('hours',r['estimated'])

    def test_step_duration_text_is_rounded_while_numeric_hours_keep_precision(self):
        plan=copy.deepcopy(self.plan)
        plan['acts'][0].update(hours=35/6,wFrom=1,wTo=2)
        with self.db.tx() as t:
            self.plans._write_steps(t,self.roadmap,plan)
            step=t.one('SELECT estimated_duration,details FROM public.roadmap_steps WHERE roadmap_id=CAST(:r AS uuid)',r=self.roadmap)
        self.assertEqual(step['estimated_duration'],'5시간 50분 · 1~2주차')
        self.assertEqual(step['details']['hours'],35/6)

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
        for invalid in ({'workDesc': '가'*501}, {'workDesc': 'Fixture', 'devYears': 51},
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
        # 새 계약은 팀 열 하나가 현재 값이다. 관리자 후속 변경이 즉시 표시된다.
        self.assertEqual(c.get('/api/v1/me/profile').json()['view']['profile']['workDesc'], 'Updated DB work description')
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
        self.assertEqual(self.db.val('SELECT planned_project_description FROM public.employees WHERE employee_id=:e', e=eid),'Personal work')
        extra=self.db.val('SELECT edited FROM app_ext.employee_self_inputs WHERE employee_id=:e', e=eid)
        self.assertNotIn('workDesc',extra)
        self.assertIn('workDescHash',extra)
        body['workDesc']='DB work'
        r = c.put('/api/v1/me/profile/self', json=body)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()['self']['edited'])
        with self.db.tx() as t:
            t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e', w='Later DB work', e=eid)
        self.assertEqual(c.get('/api/v1/me/profile').json()['view']['profile']['workDesc'], 'Later DB work')

    def test_work_description_restores_initial_team_value_and_empty_is_null(self):
        eid=self.ids['member']
        with self.db.tx() as t:
            t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e',w='처음 업무',e=eid)
        c=self.client('member')
        self.assertEqual(c.put('/api/v1/me/profile/self',json={'workDesc':'수정한 업무'}).status_code,200)
        self.assertEqual(self.db.val('SELECT baseline FROM app_ext.employee_self_inputs WHERE employee_id=:e',e=eid)['workDesc'],'처음 업무')
        self.assertEqual(c.delete('/api/v1/me/profile/self').status_code,200)
        self.assertEqual(self.db.val('SELECT planned_project_description FROM public.employees WHERE employee_id=:e',e=eid),'처음 업무')
        self.assertEqual(c.put('/api/v1/me/profile/self',json={'workDesc':''}).status_code,200)
        self.assertIsNone(self.db.val('SELECT planned_project_description FROM public.employees WHERE employee_id=:e',e=eid))
        self.assertEqual(c.put('/api/v1/me/profile/self',json={'workDesc':'가'*501}).status_code,422)

    def test_real_user_project_only_save_reaches_diagnosis_and_roadmap_handoff(self):
        from app.agents import diag,goals
        from app.services import drafts
        eid=self.ids['member']
        with self.db.tx() as t:
            t.run("UPDATE public.employees SET source_type='REAL_USER' WHERE employee_id=:e",e=eid)
        c=self.client('member')
        r=c.put('/api/v1/me/profile/self',json={'projects':['데모 가정: 로그 누락 검사 프로젝트'],'workDesc':''})
        self.assertEqual(r.status_code,200,r.text)
        v=r.json()['view']
        self.assertTrue(goals.profile_enough(v))
        self.assertIsNone(v['profile']['workDesc'])
        self.assertEqual(self.db.val('SELECT project_experience FROM public.employee_input_profiles WHERE employee_id=:e',e=eid),v['projects'][0])
        context=diag.work_profile(v)
        self.assertEqual(context['projectExperience'],v['projects'])
        self.assertNotIn('name',context)
        self.assertNotIn('code',context)
        draft={'goal':'로그 누락 검사','diag':{'startStage':1,'startReason':'응답 근거','known':[],
            'gaps':[],'competencies':[],'resourceIds':[],'outcome':''},'prefs':{'format':'','hours':'','weeks':'','budget':'','cert':'','etc':''}}
        handoff=drafts.build_handoff(draft,context)
        self.assertEqual(handoff['profile']['projectExperience'],v['projects'])
        self.assertIsNone(handoff['projectSummary'])

    def test_project_context_is_bounded_without_employee_identity(self):
        from app.agents import diag,goals
        me={'name':'private name','code':'private number','dept':'private department',
            'projects':['경험 '+str(n)+'가'*500 for n in range(8)]}
        self.assertTrue(goals.profile_enough(me))
        context=diag.work_profile(me)
        self.assertEqual(len(context['projectExperience']),5)
        self.assertTrue(all(len(x)<=300 for x in context['projectExperience']))
        self.assertNotIn('name',context)
        self.assertNotIn('department',context)
        self.assertNotIn('projectSummary',context)

    def test_question_model_receives_personal_projects_separately_from_proposal(self):
        from app.agents import diag
        ctx=SimpleNamespace(me={'profile':{'workDesc':'현재 업무'},'projects':['과거 프로젝트']})
        result={'questions':[{'text':f'검증 문항 {n}','area':'업무','skill':'SQL'} for n in range(5)]}
        def invoke(ctx,name,task,inp,mock,api,**kwargs):return api(inp)
        with patch.object(diag.rt,'run',side_effect=invoke),patch.object(diag.rt,'llm_json',return_value=result) as model, \
             patch.object(diag.DC,'build',return_value={'issues':[]}),patch.object(diag.DC,'finish',return_value=None):
            diag.questions(ctx,{'goal':'학습 목표','projectSummary':'새 기획서'})
        payload=model.call_args.args[2]
        self.assertEqual(payload['profile']['workDescription'],'현재 업무')
        self.assertEqual(payload['profile']['projectExperience'],['과거 프로젝트'])
        self.assertEqual(payload['projectSummary'],'새 기획서')

    def test_legacy_work_migration_preserves_data_and_rejects_conflicts_atomically(self):
        from sqlalchemy.exc import DBAPIError
        script=(Path(__file__).resolve().parents[2]/'backend/db/migrate_self_work_descriptions.sql').read_text(encoding='utf-8')
        # The file controls its transaction when run with psql; use this test's tx instead.
        body=script.replace('BEGIN;\nLOCK TABLE','LOCK TABLE',1).rsplit('COMMIT;',1)[0]
        first,second=self.ids['member'],self.ids['peer']
        with self.db.tx() as t:
            t.run('INSERT INTO app_ext.employee_self_inputs(employee_id,edited) VALUES(:e,:v)',e=first,v=self.db.J({'workDesc':'구판 설명'}))
            t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e',e=second,w='팀 설명')
            t.run('INSERT INTO app_ext.employee_self_inputs(employee_id,edited) VALUES(:e,:v)',e=second,v=self.db.J({'workDesc':'서로 다른 설명'}))
        with self.assertRaises(DBAPIError):
            with self.db.tx() as t:t.run(body)
        self.assertIsNone(self.db.val('SELECT planned_project_description FROM public.employees WHERE employee_id=:e',e=first))
        with self.db.tx() as t:t.run('DELETE FROM app_ext.employee_self_inputs WHERE employee_id=:e',e=second)
        for _ in range(2):
            with self.db.tx() as t:t.run(body)
        self.assertEqual(self.db.val('SELECT planned_project_description FROM public.employees WHERE employee_id=:e',e=first),'구판 설명')
        self.assertNotIn('workDesc',self.db.val('SELECT edited FROM app_ext.employee_self_inputs WHERE employee_id=:e',e=first))
        self.assertEqual(self.client('member').delete('/api/v1/me/profile/self').status_code,200)
        self.assertEqual(self.db.val('SELECT planned_project_description FROM public.employees WHERE employee_id=:e',e=first),'구판 설명')

    def _goal_setup(self):
        eid=self.ids['member']
        with self.db.tx() as t:t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e',e=eid,w='로그 분석 업무')
        return eid,{'candidates':[{'goal':f'{x} 오류를 점검하고 싶어요.','why':'업무 설명 근거','basis':['업무 설명']} for x in ('로그','적재','조회')],'note':''}

    def _wait_goal(self,eid):
        from app import jobs
        state=self.goals.get(eid)
        if state['jobId']:jobs.wait_result(state['jobId'],eid,timeout=5)
        return self.goals.get(eid)

    def test_goal_preload_first_login_reuses_cache_and_only_regenerates_for_changed_input(self):
        eid,out=self._goal_setup()
        with patch.object(self.goals,'request',self.actual_goal_request),patch.object(self.goals.G,'run',return_value=out) as generate:
            c=self.client('member')
            self.assertEqual(self._wait_goal(eid)['status'],'ready')
            self.assertEqual(generate.call_count,1)
            for _ in range(2):
                self.assertEqual(c.post('/api/v1/auth/login',json={'employeeNo':self.numbers['member'],'password':self.password}).status_code,200)
                self.assertEqual(c.get('/api/v1/me').status_code,200)
                self.assertEqual(c.post('/api/v1/me/goal-suggestions/ensure').status_code,200)
            self.assertEqual(generate.call_count,1)
            with self.db.tx() as t:t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e',e=eid,w='변경된 데이터 점검 업무')
            self.assertEqual(c.get('/api/v1/me').status_code,200)
            self.assertEqual(self._wait_goal(eid)['status'],'ready')
            self.assertEqual(generate.call_count,2)
            self.assertEqual(c.get('/api/v1/me').status_code,200)
            self.assertEqual(generate.call_count,2)

    def test_goal_concurrent_preloads_share_one_job_and_running_state_precedes_worker(self):
        eid,out=self._goal_setup()
        entered,release=Event(),Event()
        def generate(ctx,inp,**kwargs):
            self.assertEqual(self.goals.get(eid)['status'],'running')
            entered.set()
            if not release.wait(5):raise AssertionError('Test worker gate timed out')
            return out
        with patch.object(self.goals.G,'run',side_effect=generate) as model:
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    ids=list(pool.map(lambda _:self.actual_goal_request(eid,'login',only_if_stale=True),range(2)))
                self.assertTrue(entered.wait(2))
                self.assertEqual(ids[0],ids[1])
                self.assertEqual(model.call_count,1)
            finally:release.set()
            self.assertEqual(self._wait_goal(eid)['status'],'ready')

    def test_goal_failed_preload_keeps_candidates_and_only_manual_retries_same_input(self):
        from app.errors import AgentError
        eid,out=self._goal_setup()
        with self.db.tx() as t:self.goals._save(t,eid,out['candidates'])
        with patch.object(self.goals.G,'run',side_effect=AgentError('검증용 모델 연결 실패')) as generate:
            self.actual_goal_request(eid,'login',only_if_stale=True)
            self.assertEqual(self._wait_goal(eid)['status'],'failed')
            for _ in range(2):self.actual_goal_request(eid,'login',only_if_stale=True)
            self.assertEqual(generate.call_count,1)
            self.assertEqual(len(self.goals.get(eid)['candidates']),3)
        with patch.object(self.goals,'request',self.actual_goal_request),patch.object(self.goals.G,'run',return_value=out) as generate:
            self.goals.regenerate(eid)
            self.assertEqual(self._wait_goal(eid)['status'],'ready')
            self.assertEqual(generate.call_count,1)

    def test_preload_cli_defaults_to_readonly_without_model_or_job_calls(self):
        eid,_=self._goal_setup()
        before=self.db.val('SELECT count(*) FROM app_ext.jobs')
        env={**os.environ,'DATABASE_URL':self.db.engine.url.render_as_string(hide_password=False)}
        done=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve().parents[2]/'backend/tools/preload_goals.py'),
                             '--employee-id',str(eid)],env=env,capture_output=True,text=True,timeout=10)
        self.assertEqual(done.returncode,0,done.stderr)
        import json
        result=json.loads(done.stdout)
        self.assertEqual((result['mode'],result['database_writes'],result['paid_api_calls']),('preview',0,0))
        self.assertEqual(self.db.val('SELECT count(*) FROM app_ext.jobs'),before)

    def test_profile_change_during_preload_discards_old_result_and_prepares_latest_once(self):
        from app import jobs
        eid,out=self._goal_setup()
        entered,release=Event(),Event()
        inputs=[];modes=[]
        def generate(ctx,inp,**kwargs):
            value=inp['profile']['workDescription'];inputs.append(value);modes.append(ctx.mode)
            if len(inputs)==1:
                entered.set()
                if not release.wait(5):raise AssertionError('Test worker gate timed out')
            return dict(out,candidates=[dict(c,goal=value+' '+c['goal']) for c in out['candidates']])
        with patch.object(self.goals,'request',self.actual_goal_request),patch.object(self.goals.G,'run',side_effect=generate):
            try:
                jid=self.actual_goal_request(eid,'admin-preload',mode='mock',only_if_stale=True)
                self.assertTrue(entered.wait(2))
                with self.db.tx() as t:t.run('UPDATE public.employees SET planned_project_description=:w WHERE employee_id=:e',e=eid,w='바뀐 프로젝트 점검 업무')
                self.assertEqual(self.actual_goal_request(eid,'self-input',only_if_stale=True),jid)
            finally:release.set()
            jobs.wait_result(jid,eid,timeout=5)
            state=self._wait_goal(eid)
            self.assertEqual(state['status'],'ready')
            self.assertEqual(inputs,['로그 분석 업무','바뀐 프로젝트 점검 업무'])
            self.assertEqual(modes,['mock','mock'])
            self.assertTrue(all(c['goal'].startswith('바뀐 프로젝트 점검 업무') for c in state['candidates']))

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
