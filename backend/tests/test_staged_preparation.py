from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import test_generation_concurrency as concurrency
import test_survey_generation as fixture
from test_issue67_scenarios import SurveyMemory
from app.routers import preassessment as api
from app.services import survey_store as store,post_quiz

class StagedPreparationTests(TestCase):
    setUp=concurrency.GenerationConcurrencyTests.setUp
    def test_surveys_visible_before_quizzes_and_saved_answers_survive(self):
        f=fixture.SurveyTests();f.setUp()
        project={k:v for k,v in f.project.items() if k!='rawText'}
        project['selectedSkills']=f.selection(2)['skills']
        memory=SurveyMemory({'goal':project['goal']})
        started,release=Event(),Event();calls=[]
        @contextmanager
        def transaction():yield memory
        def model(ctx,system,payload):
            phase='surveys' if payload['surveysPerSkill'] else 'quizzes';calls.append(phase)
            if phase=='quizzes':
                started.set()
                if not release.wait(5):raise AssertionError('quiz barrier timeout')
            result=f.result(2)
            for group in result['groups']:
                group['quizzes' if phase=='surveys' else 'surveys']=[]
                for q in group['quizzes']:q.update(concept=q['q'],questionType='오류 원인 판단',difficulty='적용')
            return result
        with patch.object(api.db,'tx',side_effect=transaction),patch.object(api,'project_input',return_value=project),patch.object(api.profile,'view',return_value=f.profile),patch.object(api,'profile_input',side_effect=lambda x:x),patch('app.catalog.skill_names',return_value=['스킬0','스킬1']),patch.object(api.runtime,'context',return_value=SimpleNamespace(live=True)),patch.object(api.runtime,'llm_json',side_effect=model):
            with ThreadPoolExecutor(max_workers=1) as pool:
                job=pool.submit(api.generate_for,1,'p',staged=True)
                try:
                    self.assertTrue(started.wait(3))
                    partial=store.read(memory,1,'p');gid=partial['generationId']
                    self.assertEqual(partial['quizStatus'],'pending')
                    self.assertTrue(all(g['surveys'] and not g['quizzes'] for g in partial['survey']['groups']))
                    answers={q['id']:3 for g in partial['survey']['groups'] for q in g['surveys']}
                    store.save_answers(memory,1,'p',gid,answers,complete=False)
                    with self.assertRaises(store.StoreError):store.save_answers(memory,1,'p',gid,answers,complete=True)
                finally:release.set()
                final=job.result(timeout=5)
            self.assertEqual(final['generationId'],gid)
            self.assertEqual(final['answers'],answers)
            self.assertEqual(final['quizStatus'],'ready')
            self.assertTrue(all(g['quizzes'] for g in final['groups']))
            api.generate_for(1,'p',staged=True)
            self.assertEqual(calls,['surveys','quizzes'])

    def test_saved_five_skill_survey_can_finish_failed_quizzes(self):
        """이전 상한(5개)으로 설문까지 저장된 점검은 퀴즈 재시도로 완료할 수 있다."""
        from functools import partial
        from app.agents.survey_generation import generate_survey
        f=fixture.SurveyTests();f.setUp()
        project={k:v for k,v in f.project.items() if k!='rawText'}
        project['selectedSkills']=f.selection(5)['skills']
        memory=SurveyMemory({'goal':project['goal']})
        @contextmanager
        def transaction():yield memory
        surveys=f.result(5)
        for group in surveys['groups']:group['quizzes']=[]
        with patch.object(store,'generate_survey',partial(generate_survey,max_skills=5)):
            saved=store.save_generated(memory,1,'p',project,f.selection(5),f.profile,surveys,phase='surveys')
        value=deepcopy(memory.raw['v2Survey'])
        value['quizStatus']='failed';store._write(memory,1,'p',value)
        calls=[]
        def model(ctx,system,payload):
            calls.append(payload['quizzesPerSkill'] and 'quizzes')
            result=f.result(5)
            for group in result['groups']:
                group['surveys']=[]
                for q in group['quizzes']:q.update(concept=q['q'],questionType='오류 원인 판단',difficulty='적용')
            return result
        names=[row['name'] for row in f.selection(5)['skills']]
        with patch.object(api.db,'tx',side_effect=transaction),patch.object(api,'project_input',return_value=project),patch.object(api.profile,'view',return_value=f.profile),patch.object(api,'profile_input',side_effect=lambda x:x),patch('app.catalog.skill_names',return_value=names),patch.object(api.runtime,'context',return_value=SimpleNamespace(live=True)),patch.object(api.runtime,'llm_json',side_effect=model):
            final=api.generate_for(1,'p',staged=True)
        self.assertEqual(calls,['quizzes'])
        self.assertEqual(final['generationId'],saved['generationId'])
        self.assertEqual(final['quizStatus'],'ready')
        self.assertEqual([g['skill'] for g in final['groups']],names)
        self.assertTrue(all(len(g['quizzes'])==3 for g in final['groups']))

    def test_confirm_preparation_queues_and_cached_post_quiz_is_reused(self):
        plan={'assess':{'v2':{'survey':{'groups':[{'skill':'S','quizzes':[{'id':'q'}]}]}}}}
        from app import jobs,db
        from app.services import plans
        with patch('app.services.generation_job.start_shared',return_value='job') as start:
            self.assertEqual(post_quiz.prepare(1,'p',plan),'job')
            self.assertEqual(start.call_args.args[:2],(1,'post-quiz:p'))
        with patch.object(plans,'_owned',return_value={'status':'IN_PROGRESS','roadmap_id':'p','content':plan}),patch.object(db,'one',return_value={'deep':{'v2Quiz':{'cached':True}}}),patch.object(post_quiz,'generate') as model:
            self.assertEqual(post_quiz.ensure_generated(1,'p'),{'cached':True})
            model.assert_not_called()
        with patch.object(plans,'records',return_value={'p':{'id':'p','status':'active','plan':plan,'versions':[plan],'post':{'quizSurvey':None}}}),patch.object(plans,'reports',return_value=[]),patch.object(plans,'resources_of',return_value={}),patch.object(post_quiz,'prepare') as prep:
            plans.workspace(1)
            prep.assert_called_once_with(1,'p',plan)
    def test_material_preparation_is_version_scoped_and_reuses_pending_job(self):
        from app.services import material_preparation as material,drafts
        from app import db,jobs
        raw={'v2Survey':{'completed':True},'draft':{'gen':{'options':{'A1':{'optionId':'free-v1'},'A2':{'optionId':'crash-v1'}}}}}
        @contextmanager
        def transaction():yield object()
        queued=[]
        def start(kind,employee,ref,work):queued.append((ref,work));return 'job'+str(len(queued))
        try:
            with patch.object(db,'tx',side_effect=transaction),patch.object(drafts,'_row',return_value={'draft_choices':raw}),patch.object(jobs,'start',side_effect=start):
                material.prepare(1,'p');material.prepare(1,'p')
                self.assertEqual(len(queued),2)
                self.assertEqual(material.pending(1,'p','A1',raw['draft']['gen']['options']['A1']),'job1')
                raw['draft']['gen']['options']['A2']={'optionId':'crash-v2'}
                material.prepare(1,'p',['A2'])
                self.assertEqual(len(queued),3)
                self.assertTrue(queued[-1][0].startswith('p:A2:'))
                self.assertEqual(queued[1][1](None),{})
        finally:
            with material._lock:material._flights.clear()
