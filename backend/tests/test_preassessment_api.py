import copy
from contextlib import contextmanager
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from fastapi import FastAPI
from app.errors import api_error_handler
from app.routers import preassessment as api
from app.auth import Account, require_employee
import test_survey_generation as fixtures
api_app=FastAPI()
api_app.include_router(api.r)
api_app.add_exception_handler(api.ApiError,api_error_handler)
for error_type in (api.StoreError,api.SelectionError,api.SurveyError,api.RecommendationError):
    api_app.add_exception_handler(error_type,api.validation_error)


@contextmanager
def transaction(t):
    yield t


class ApiTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.SurveyTests(); fixture.setUp()
        self.fixture = fixture
        self.pid = str(uuid4())
        self.project = {'goal': '전처리와 모델 비교', 'desiredCompetencies': '전처리와 모델 비교', 'projectSummary': '예측·검증 포함. 자동 제어 제외.'}
        self.me = {'dept': '운영부', 'education': ['대학교 통계전공 (학사)'], 'profile': {'workDesc': '수질 분석'},
                   'tech': ['Python'], 'projects': ['분석 경험'], 'certs': [], 'learning': []}
        self.survey = fixture.run_result(fixture.result(2))
        self.saved = {'profile': api.profile_input(self.me), 'version': 1, 'generationId': str(uuid4()), 'project': self.project,
                      'survey': self.survey, 'answers': {}, 'completed': False}
        self.client = TestClient(api_app)
        api_app.dependency_overrides.clear()

    def tearDown(self):
        api_app.dependency_overrides.clear()

    def auth(self):
        api_app.dependency_overrides[require_employee] = lambda: Account('employee', 7, '시험')

    def test_all_endpoints_require_authentication(self):
        for method, path in [('GET', '/api/v2/drafts'), ('GET', f'/api/v2/drafts/{self.pid}/survey'),
                             ('POST', f'/api/v2/drafts/{self.pid}/survey')]:
            with self.subTest(method=method), patch.object(api.db, 'all_') as query:
                self.assertEqual(self.client.request(method, path).status_code, 401)
                query.assert_not_called()

    def test_listing_is_scoped_to_logged_in_employee(self):
        self.auth()
        with patch.object(api.db, 'all_', return_value=[{'project_id': self.pid, 'project_name': '시험 초안', 'project_goal': '목표'}]) as query:
            response = self.client.get('/api/v2/drafts')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(query.call_args.kwargs['e'], 7)
        self.assertEqual(response.json()['drafts'][0]['id'], self.pid)

    def test_read_has_no_private_profile_or_answers_to_quiz(self):
        self.auth()
        t = Mock()
        with patch.object(api.db, 'tx', side_effect=lambda: transaction(t)), patch.object(api, 'read', return_value=self.saved), patch.object(api, 'project_input', return_value=self.project), patch.object(api.profile, 'view', return_value=self.me):
            response = self.client.get(f'/api/v2/drafts/{self.pid}/survey')
        body = response.json()['survey']
        self.assertNotIn('profile', body)
        for group in body['groups']:
            for quiz in group['quizzes']:
                self.assertNotIn('answer', quiz)
                self.assertNotIn('explain', quiz)

    def test_answer_endpoint_rejects_bool_float_extra_fields_and_bad_uuid(self):
        self.auth()
        valid = {'generationId': self.saved['generationId'], 'answers': {'q': 0}, 'complete': False}
        for body in (dict(valid, answers={'q': True}), dict(valid, answers={'q': 1.2}),
                     dict(valid, employeeId=99), dict(valid, generationId='bad'), dict(valid, complete='false')):
            with self.subTest(body=body), patch.object(api, 'save_answers') as save:
                self.assertEqual(self.client.put(f'/api/v2/drafts/{self.pid}/survey/answers', json=body).status_code, 422)
                save.assert_not_called()

    def test_answers_use_session_employee_and_preserve_zero(self):
        self.auth()
        t = Mock()
        with patch.object(api.db, 'tx', side_effect=lambda: transaction(t)), patch.object(api, 'save_answers', return_value=self.saved) as save, patch.object(api, 'read', return_value=self.saved), patch.object(api, 'project_input', return_value=self.project), patch.object(api.profile, 'view', return_value=self.me):
            response = self.client.put(f'/api/v2/drafts/{self.pid}/survey/answers', json={'generationId': self.saved['generationId'], 'answers': {'q': 0}, 'complete': False})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(save.call_args.args[1:3], (7, self.pid))
        self.assertEqual(save.call_args.args[4], {'q': 0})

    def test_project_reads_only_completed_summary_and_goal(self):
        t = Mock()
        t.one.return_value = {'draft_choices': {'draft': {'goal': self.project['goal'], 'project': {'name': 'test.pdf'}, 'doc': {'status': 'ok', 'summary': self.project['projectSummary'], 'text': 'RAW SECRET'}}}}
        self.assertEqual({k: api.project_input(t, 7, self.pid)[k] for k in self.project}, self.project)
        t.one.return_value['draft_choices']['draft']['doc']['status'] = 'reading'
        with self.assertRaises(api.ApiError): api.project_input(t, 7, self.pid)
        t.one.return_value = None
        with self.assertRaises(api.ApiError) as error: api.project_input(t, 7, self.pid)
        self.assertEqual(error.exception.status, 404)

    def test_project_is_optional_but_attached_file_waits_for_summary(self):
        t = Mock()
        t.one.return_value = {'draft_choices': {'draft': {'goal': 'Python으로 데이터 분석'}}}
        project = api.project_input(t, 7, self.pid)
        self.assertIsNone(project['projectSummary'])
        self.assertEqual(project['desiredCompetencies'], 'Python으로 데이터 분석')
        t.one.return_value['draft_choices']['draft']['project'] = {'name': 'test.pdf'}
        with self.assertRaises(api.ApiError) as error:
            api.project_input(t, 7, self.pid)
        self.assertEqual(error.exception.code, 'PROJECT_SUMMARY_PENDING')

    def test_existing_survey_reuses_without_model_calls(self):
        t = Mock()
        with patch.object(api.db, 'tx', side_effect=lambda: transaction(t)), patch.object(api, 'project_input', return_value=self.project), patch.object(api, 'read', return_value=self.saved), patch.object(api.runtime, 'context') as ctx, patch.object(api.profile, 'view', return_value=self.me):
            result = api.generate_for(7, self.pid)
        self.assertEqual(result['generationId'], self.saved['generationId'])
        ctx.assert_not_called()

    def test_generation_uses_db_profile_and_two_generation_functions(self):
        t = Mock(); selection = self.fixture.selection(2)
        with patch.object(api.db, 'tx', side_effect=lambda: transaction(t)), patch.object(api, 'project_input', return_value=self.project), patch.object(api, 'read', return_value=None), patch.object(api.profile, 'view', return_value=self.me), patch.object(api.runtime, 'context', return_value=Mock(live=True)), patch.object(api, 'select_from_catalog', return_value=selection) as select, patch.object(api, 'generate_survey', return_value=self.survey) as generate, patch.object(api, 'save_generated', return_value=self.saved) as save:
            api.generate_for(7, self.pid)
        select.assert_called_once()
        self.assertEqual(generate.call_args.args[0], self.project)
        self.assertEqual(generate.call_args.args[1], selection)
        self.assertEqual(generate.call_args.args[2]['self']['projects'], self.me['projects'])
        self.assertEqual(generate.call_args.args[2]['education'], self.me['education'])
        save.assert_called_once()

    def test_changed_input_after_generation_never_saves(self):
        t = Mock()
        with patch.object(api.db, 'tx', side_effect=lambda: transaction(t)), patch.object(api, 'project_input', side_effect=[self.project, dict(self.project, goal='변경')]), patch.object(api, 'read', return_value=None), patch.object(api.profile, 'view', return_value=self.me), patch.object(api.runtime, 'context', return_value=Mock(live=True)), patch.object(api, 'select_from_catalog', return_value=self.fixture.selection(2)), patch.object(api, 'generate_survey', return_value=self.survey), patch.object(api, 'save_generated') as save:
            with self.assertRaises(api.ApiError) as error: api.generate_for(7, self.pid)
        self.assertEqual(error.exception.code, 'SURVEY_INPUT_CHANGED')
        save.assert_not_called()

    def test_busy_generation_is_rejected_before_db_or_model(self):
        api._generation_lock.acquire()
        try:
            with patch.object(api.db, 'tx') as query, self.assertRaises(api.ApiError) as error:
                api.generate_for(7, self.pid)
            self.assertEqual(error.exception.code, 'GENERATION_BUSY')
            query.assert_not_called()
        finally:
            api._generation_lock.release()


    def test_changed_input_is_not_returned_as_current_survey(self):
        self.auth(); t = Mock()
        changed = dict(self.project, goal='새로운 희망')
        with patch.object(api.db, 'tx', side_effect=lambda: transaction(t)), patch.object(api, 'read', return_value=self.saved), patch.object(api, 'project_input', return_value=changed), patch.object(api.profile, 'view', return_value=self.me):
            response = self.client.get(f'/api/v2/drafts/{self.pid}/survey')
        self.assertEqual(response.json(), {'survey': None, 'stale': True})

    def test_changed_input_blocks_old_answer_submission(self):
        self.auth(); t = Mock()
        with patch.object(api.db, 'tx', side_effect=lambda: transaction(t)), patch.object(api, 'read', return_value=self.saved), patch.object(api, 'project_input', return_value=dict(self.project, goal='변경')), patch.object(api.profile, 'view', return_value=self.me), patch.object(api, 'save_answers') as save:
            response = self.client.put(f'/api/v2/drafts/{self.pid}/survey/answers', json={'generationId': self.saved['generationId'], 'answers': {}, 'complete': False})
        self.assertEqual(response.status_code, 409)
        save.assert_not_called()

    def test_regeneration_targets_previous_generation_and_new_inputs(self):
        t = Mock(); changed = dict(self.project, details={'hours': '6'})
        with patch.object(api.db, 'tx', side_effect=lambda: transaction(t)), patch.object(api, 'project_input', return_value=changed), patch.object(api, 'read', return_value=self.saved), patch.object(api.profile, 'view', return_value=self.me), patch.object(api.runtime, 'context', return_value=Mock(live=True)), patch.object(api, 'select_from_catalog', return_value=self.fixture.selection(2)), patch.object(api, 'generate_survey', return_value=self.survey), patch.object(api, 'save_generated', return_value=self.saved) as save:
            api.generate_for(7, self.pid)
        self.assertEqual(save.call_args.kwargs['replace_generation_id'], self.saved['generationId'])
        self.assertEqual(save.call_args.args[3], changed)

    def test_profile_or_file_or_details_change_invalidates_survey(self):
        personal = api.profile_input(self.me)
        self.assertTrue(api.inputs_match(self.saved, self.project, personal))
        for extra in ({'details': {'weeks': '7'}}, {'projectFile': {'name': 'other.pdf'}}, {'projectSourceHash': 'changed'}):
            self.assertFalse(api.inputs_match(self.saved, dict(self.project, **extra), personal))
        changed = dict(personal, department='다른 소속')
        self.assertFalse(api.inputs_match(self.saved, self.project, changed))


    def test_old_generation_token_is_rejected_even_when_inputs_match(self):
        self.auth(); t = Mock()
        with patch.object(api.db, 'tx', side_effect=lambda: transaction(t)), patch.object(api, 'read', return_value=self.saved), patch.object(api, 'project_input', return_value=self.project), patch.object(api.profile, 'view', return_value=self.me), patch.object(api, 'save_answers') as save:
            response = self.client.put(f'/api/v2/drafts/{self.pid}/survey/answers', json={'generationId': str(uuid4()), 'answers': {}, 'complete': False})
        self.assertEqual(response.status_code, 409)
        save.assert_not_called()

    def test_recommendations_require_completed_assessment(self):
        self.auth(); t=Mock()
        with patch.object(api.db,'tx',side_effect=lambda:transaction(t)),patch.object(api,'read',return_value=self.saved):
            response=self.client.get(f'/api/v2/drafts/{self.pid}/recommendations')
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['error']['code'],'ASSESSMENT_REQUIRED')

    def test_existing_recommendations_are_read_without_model_calls(self):
        self.auth(); t=Mock(); saved=dict(self.saved,completed=True,recommendations={'id':'rec','skills':[],'retrieval':{'version':'resource-pgvector-rag/v2'}},resourceChoices={})
        with patch.object(api.db,'tx',side_effect=lambda:transaction(t)),patch.object(api,'recommendation_context',return_value=saved),patch.object(api,'recommend_from_catalog') as generate:
            response=self.client.get(f'/api/v2/drafts/{self.pid}/recommendations')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['recommendations']['id'],'rec')
        generate.assert_not_called()

    def test_old_keyword_cache_requires_regeneration_without_get_model_call(self):
        self.auth(); saved=dict(self.saved,completed=True,recommendations={'id':'old','skills':[]})
        with patch.object(api.db,'tx',side_effect=lambda:transaction(Mock())),patch.object(api,'recommendation_context',return_value=saved),patch.object(api,'recommend_from_catalog') as generate:
            response=self.client.get(f'/api/v2/drafts/{self.pid}/recommendations')
        self.assertIsNone(response.json()['recommendations'])
        generate.assert_not_called()

    def test_changed_assessment_blocks_recommendation_save(self):
        self.auth()
        with patch.object(api.db,'tx',side_effect=lambda:transaction(Mock())),patch.object(api,'recommendation_context',side_effect=api.ApiError(409,'SURVEY_INPUT_CHANGED','변경')),patch.object(api,'save_resource_choices') as save:
            response=self.client.put(f'/api/v2/drafts/{self.pid}/recommendations/choices',json={'generationId':str(uuid4()),'recommendationId':str(uuid4()),'choices':{}})
        self.assertEqual(response.status_code,409)
        save.assert_not_called()

    def test_duration_calculation_never_calls_model_or_generation_lock(self):
        self.auth(); rid=str(uuid4())
        rec={'id':rid,'skills':[{'name':'S','courses':[{'id':'c','hours':8}],'books':[{'id':'b'}]}]}
        saved=dict(self.saved,completed=True,recommendations=rec,skillOrder=['S'],resourceChoices={'S':{'course':'c','books':['b']}})
        with patch.object(api.db,'tx',side_effect=lambda:transaction(Mock())),patch.object(api,'course_context',return_value=saved),patch.object(api,'course_input',return_value={'weeklyHours':4}),patch.object(api,'save_duration_proposals',side_effect=lambda *args,**kwargs:dict(saved,durationEstimates=args[5])),patch.object(api.runtime,'context') as context,patch.object(api.runtime,'llm_json') as generate,patch.object(api,'_generation_lock') as lock:
            response=self.client.post(f'/api/v2/drafts/{self.pid}/recommendations/durations?course=A2',json={'generationId':saved['generationId'],'recommendationId':rid,'choices':saved['resourceChoices'],'skillOrder':['S']})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['durationEstimates']['S']['weeks'],3)
        context.assert_not_called();generate.assert_not_called();lock.acquire.assert_not_called()
