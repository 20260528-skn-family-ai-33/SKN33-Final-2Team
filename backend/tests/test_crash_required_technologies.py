"""사용자 원문과 구조화된 스킬을 계획 생성·수정·추천 경계에서 확인한다."""
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
import json
import unittest
from unittest.mock import Mock, patch

from app import db
from app.agents import roadmap, runtime
from app.errors import ApiError
from app.routers import preassessment
from app.services import course_skills, drafts, resource_evidence, resource_rag
import test_revision_course_targets as revision_cases
from test_recommendation_suitability import WEB, course


def target(technology='FastAPI', **changes):
    return dict({'name': WEB, 'application': 'Django와 FastAPI로 REST API 개발',
                 'coreOutcome': f'{technology} REST API 구현',
                 'coreCriteria': [f'{technology} REST API 구현과 테스트'],
                 'followUpScope': ['Django 심화 비교']}, **changes)


class CrashRequiredTechnologiesTests(unittest.TestCase):
    def option(self, answer, *, goal='Django 사용 필수', request=None, previous=None, mock=False):
        handoff = {'goal': goal, 'assessmentGenerationId': 'g', 'selectedSkillsFixed': True,
                   'courseSkillSelection': True, 'skillNames': [WEB], 'skillOrder': [WEB],
                   'skillDetails': [{'name': WEB, 'application': 'Django와 FastAPI로 REST API 개발'}]}
        inp = {'pid': 'A2', 'handoff': handoff}
        if request is not None:
            inp['request'] = request
        if previous is not None:
            inp.update(previousDef=previous, previous={'acts': []}, variant=1)
        before, raw_before = deepcopy(inp), deepcopy(answer)
        captured = {}
        def model(ctx, system, payload, **kwargs):
            captured.update(system=system, payload=deepcopy(payload))
            return {'acts': [], 'learningSkills': [deepcopy(answer)]}
        with patch.object(roadmap, '_sys', return_value='[통합 생성 계약 roadmap-generation/v1]'), \
             patch.object(roadmap.catalog, 'skill_names', return_value=[WEB]), \
             patch.object(roadmap, '_catalog_payload', side_effect=lambda pid, payload, *args: deepcopy(payload)), \
             patch.object(roadmap.rt, 'llm_json', side_effect=model), \
             patch.object(roadmap, '_validate_learning_acts'), \
             patch.object(roadmap, 'finish_option', side_effect=lambda *args, **kwargs: {'id': 'A2', 'acts': []}), \
             patch.object(roadmap, '_mock_option', return_value={'id': 'A2', 'acts': [], 'learningSkills': [answer]}), \
             patch.object(roadmap.rt, 'run', side_effect=lambda ctx, name, task, data, demo, api, **kw: demo(data) if mock else api(None)):
            try:
                result = roadmap.option(SimpleNamespace(mode='mock' if mock else 'openai'), inp)
            finally:
                self.assertEqual(inp, before)
                self.assertEqual(answer, raw_before)
        return result, captured

    def test_generation_and_regeneration_pass_raw_goal_without_a_technology_gate(self):
        goal = 'Django 또는 FastAPI 중 하나 또는 Redis 필수'
        request = {'wish': '기술은 위 조건 중 하나만 사용'}
        for previous in (None, {'learningSkills': [target('FastAPI')]}):
            with self.subTest(regenerate=previous is not None):
                result, captured = self.option(target('Redis'), goal=goal, request=request if previous else None, previous=previous)
                self.assertEqual(captured['payload']['handoff']['goal'], goal)
                self.assertEqual(captured['payload']['request'], request if previous else None)
                self.assertNotIn('[사용자가 명시한 필수 기술]', captured['system'])
                self.assertEqual(result['learningSkills'][0]['coreOutcome'], 'Redis REST API 구현')

    def test_revision_passes_raw_request_and_uses_course_specific_target_shape(self):
        helper = revision_cases.CourseTransitionTargetsTests()
        for source in ('A3', 'A2'):
            with self.subTest(source=source):
                inp = helper.revision_input(source, 'A2', names=[WEB])
                inp['request'] = 'Django 또는 FastAPI 중 하나 또는 Redis 필수'
                inp['plan']['def']['learningSkills'] = [target('FastAPI')]
                result, captured, _ = helper.revise_input(inp, [target('Redis')])
                self.assertEqual(captured['payload']['request'], inp['request'])
                self.assertNotIn('[사용자가 명시한 필수 기술]', captured['system'])
                expected = 'Redis' if source == 'A3' else 'FastAPI'
                self.assertEqual(result['learningSkills'][0]['coreOutcome'], expected + ' REST API 구현')

    def test_course_transition_keeps_valid_core_and_completed_activity(self):
        helper = revision_cases.CourseTransitionTargetsTests()
        inp = helper.revision_input('A3', 'A2', names=[WEB])
        inp['handoff']['goal'] = 'Django 사용 필수'
        result, _, plan = helper.revise_input(inp, [target('Django')])
        self.assertEqual(result['learningSkills'][0]['coreOutcome'], 'Django REST API 구현')
        self.assertEqual(result['acts'][0]['key'], plan['acts'][0]['id'])
        self.assertTrue(plan['acts'][0]['done'])

    def test_legacy_initialization_validates_before_saving(self):
        option = {'id': 'A2', 'name': 'Crash', 'acts': [{'title': '기존 활동'}]}
        wrapper = {'draft': {'gen': {'options': {'A2': option}}}}
        saved = {'generationId': 'g', 'selection': {'skills': [{'name': WEB}]},
                 'project': {'goal': 'Django 또는 FastAPI 중 하나 또는 Redis 필수'}}
        def mutate(employee_id, project_id, write):
            write(Mock(), wrapper)
            return wrapper
        with patch.object(course_skills, 'generation_guard', side_effect=lambda *args: nullcontext()), \
             patch.object(db, 'tx', side_effect=lambda: nullcontext(Mock())), \
             patch.object(preassessment, 'recommendation_context', return_value=saved), \
             patch.object(drafts, '_row', return_value={'draft_choices': wrapper}), \
             patch.object(drafts, '_wrap', side_effect=lambda value: value), \
             patch.object(drafts, '_mutate', side_effect=mutate), patch.object(drafts, 'present'), \
             patch.object(runtime, 'context', return_value=SimpleNamespace(live=True)), \
             patch.object(runtime, 'llm_json', return_value={'learningSkills': [target('Redis')]}) as model:
            course_skills.initialize(1, 'project', 'A2')
            self.assertEqual(model.call_args.args[2]['handoff']['goal'], saved['project']['goal'])
            self.assertNotIn('[사용자가 명시한 필수 기술]', model.call_args.args[1])
            self.assertEqual(option['learningSkills'][0]['coreOutcome'], 'Redis REST API 구현')
            del option['learningSkills']
            model.return_value = {'learningSkills': [target('Redis', coreCriteria=[])]}
            with self.assertRaises(ApiError) as caught:
                course_skills.initialize(1, 'project', 'A2')
            self.assertEqual(caught.exception.code, 'SKILLS_INVALID')
            self.assertNotIn('learningSkills', option)

    def test_validated_required_core_reaches_search_and_actual_suitability(self):
        result, _ = self.option(target('Django'))
        skill = result['learningSkills'][0]
        project, selection = {'goal': 'Django 사용 필수'}, {'skills': [skill]}
        query = json.loads(resource_rag.query_text(project, skill, result))
        self.assertIn('Django', query['coreOutcome'])
        self.assertNotIn('followUpScope', query)
        good = course('django', ['Django REST API 구현 실습'], skills=[WEB])
        wrong = course('fastapi', ['FastAPI REST API 구현 실습'], skills=[WEB])
        good_info = resource_evidence.facts(good, project, selection)
        wrong_info = resource_evidence.facts(wrong, project, selection)
        self.assertTrue(resource_evidence.suitable(good_info, WEB))
        self.assertFalse(resource_evidence.suitable(wrong_info, WEB))
        self.assertEqual(wrong_info['suitability'][WEB]['missingStack'], ['django'])

    def test_optional_comparison_stays_out_of_search_and_suitability(self):
        result, _ = self.option(target(), goal='FastAPI 구현 후 Django 비교')
        skill = result['learningSkills'][0]
        project = {'goal': 'FastAPI 구현 후 Django 비교'}
        query = resource_rag.query_text(project, skill, result)
        self.assertNotIn('django', query.casefold())
        row = course('fastapi', ['FastAPI REST API 구현 실습'], skills=[WEB])
        info = resource_evidence.facts(row, project, {'skills': [skill]})
        self.assertTrue(resource_evidence.suitable(info, WEB))
        self.assertEqual(info['suitability'][WEB]['requiredStack'], ['fastapi'])
