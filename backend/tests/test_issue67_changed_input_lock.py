"""입력 변경 중 이전 설문 생성 잠금의 영향 재현. 실제 DB·모델 미사용."""
from contextlib import contextmanager
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch
from unittest import TestCase
import test_generation_concurrency as concurrency
from app.routers import preassessment as api
from app.errors import ApiError

class ChangedInputLockTests(TestCase):
    setUp = concurrency.GenerationConcurrencyTests.setUp
    def test_old_survey_does_not_block_new_skills_and_late_survey_is_rejected(self):
        started, release = Event(), Event()
        project = {'goal':'기존 목표','projectSummary':'가상 프로젝트'}
        @contextmanager
        def transaction():
            yield Mock()
        def generate(*args, **kwargs):
            started.set()
            if not release.wait(5): raise AssertionError('test barrier timeout')
            return {'groups':[]}
        with patch.object(api.db,'tx',side_effect=transaction), patch.object(api.profile,'view',return_value={}), patch.object(api,'profile_input',return_value={}), patch.object(api,'project_input',side_effect=lambda *a:deepcopy(project)), patch.object(api,'read',return_value=None), patch.object(api.runtime,'context',return_value=SimpleNamespace(live=True)), patch.object(api,'select_from_catalog',return_value=[{'name':'S'}]) as skills, patch.object(api,'generate_survey',side_effect=generate), patch.object(api,'save_generated') as save:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(api.generate_for,1,'project')
                try:
                    self.assertTrue(started.wait(3))
                    project['goal']='변경된 목표'
                    self.assertEqual(api.preview_skills('project',SimpleNamespace(id=1)),[{'name':'S'}])
                    self.assertEqual(skills.call_count,2)
                finally:
                    release.set()
                with self.assertRaises(ApiError) as stale:
                    pending.result(timeout=5)
                self.assertEqual(stale.exception.code,'SURVEY_INPUT_CHANGED')
            save.assert_not_called()
            self.assertEqual(api.preview_skills('project',SimpleNamespace(id=1)),[{'name':'S'}])
            self.assertFalse(self.memory.held)

    def test_same_input_blocks_duplicate_but_changed_input_runs_and_old_result_is_rejected(self):
        project={'goal':'기존 목표'}
        personal={'name':'old'}
        started,release=Event(),Event()
        @contextmanager
        def transaction(): yield Mock()
        def model(ctx,payload):
            if payload['goal']=='기존 목표':
                started.set()
                if not release.wait(5):raise AssertionError('test barrier timeout')
            return {'skills':[{'name':'new'}]}
        with patch.object(api.db,'tx',side_effect=transaction),patch.object(api.profile,'view',side_effect=lambda *_:deepcopy(personal)),patch.object(api,'profile_input',side_effect=lambda x:x),patch.object(api,'project_input',side_effect=lambda *a:deepcopy(project)),patch.object(api.runtime,'context',return_value=SimpleNamespace(live=True)),patch.object(api,'select_from_catalog',side_effect=model):
            with ThreadPoolExecutor(max_workers=1) as pool:
                old=pool.submit(api.preview_skills,'project',SimpleNamespace(id=1))
                try:
                    self.assertTrue(started.wait(3))
                    with self.assertRaises(ApiError) as busy:api.preview_skills('project',SimpleNamespace(id=1))
                    self.assertEqual(busy.exception.code,'GENERATION_BUSY')
                    project['goal']='새 목표'
                    self.assertEqual(api.preview_skills('project',SimpleNamespace(id=1)),{'skills':[{'name':'new'}]})
                finally:release.set()
                with self.assertRaises(ApiError) as stale:old.result(timeout=5)
                self.assertEqual(stale.exception.code,'SKILL_INPUT_CHANGED')
            self.assertFalse(self.memory.held)

    def test_profile_change_rejects_result_and_independent_preferences_do_not(self):
        project={'goal':'목표','details':{'hours':3},'selectedSkills':[{'name':'S'}]}
        personal={'self':{'tech':['Python']}}
        @contextmanager
        def transaction():yield Mock()
        def model(ctx,payload):
            project['details']['hours']=8
            project['selectedSkills']=[]
            return {'skills':[]}
        with patch.object(api.db,'tx',side_effect=transaction),patch.object(api.profile,'view',side_effect=lambda *_:deepcopy(personal)),patch.object(api,'profile_input',side_effect=lambda x:x),patch.object(api,'project_input',side_effect=lambda *a:deepcopy(project)),patch.object(api.runtime,'context',return_value=SimpleNamespace(live=True)),patch.object(api,'select_from_catalog',side_effect=model) as generate:
            self.assertEqual(api.preview_skills('project',SimpleNamespace(id=1)),{'skills':[]})
            def changed(ctx,payload):
                personal['self']['tech'].append('SQL')
                return {'skills':[]}
            generate.side_effect=changed
            with self.assertRaises(ApiError) as stale:api.preview_skills('project',SimpleNamespace(id=1))
            self.assertEqual(stale.exception.code,'SKILL_INPUT_CHANGED')
        self.assertFalse(self.memory.held)
