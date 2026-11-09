"""#91: 필수 기술은 생성·수정 검증을 통과한 핵심으로 검색/자료 판정까지 이어진다."""
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
import json
import unittest
from unittest.mock import Mock, patch

from app import db, llm
from app.agents import roadmap, runtime
from app.errors import ApiError
from app.routers import preassessment
from app.services import course_skills, drafts, resource_evidence, resource_rag
from app.services.crash_requirements import MAX_REQUIREMENT_CHARS, _requirement_groups, required_technologies, validate_core_requirements
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
            captured['system'] = system
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

    def test_generation_rejects_required_technology_only_in_follow_up_or_application(self):
        with self.assertRaisesRegex(llm.LlmError, '(?i)django'):
            self.option(target())

    def test_generation_accepts_required_core_and_sends_requirement_to_model(self):
        result, captured = self.option(target('Django'))
        self.assertEqual(result['learningSkills'][0]['coreCriteria'], ['Django REST API 구현과 테스트'])
        self.assertIn('필수 기술', captured['system'])
        self.assertIn('django', captured['system'].casefold())
        self.assertIn('기술 이름을 문장에 그대로', captured['system'])

    def test_core_must_name_the_technology_not_only_its_components(self):
        # 실제 모델 응답에서 나온 두 문장이다. 기술 이름이 없으면 거절하므로 프롬프트가 이름을 요구한다.
        for goal, outcome in (('Docker 사용 필수', '웹 서비스 Dockerfile로 실행 가능한 이미지를 생성해요.'),
                              ('Kubernetes 필수', '샘플 서비스를 Deployment와 Service로 배포해요.')):
            with self.subTest(goal=goal), self.assertRaises(llm.LlmError):
                self.option(self.paired_core(outcome), goal=goal)

    def test_versioned_requirement_and_substitution_reach_final_generation_validation(self):
        goal = 'Django 5.2 사용 필수'

        def answer(outcome):
            return target(coreOutcome=outcome, coreCriteria=['응답 코드 확인'])

        result, captured = self.option(answer('FastAPI 대신 Django로 API 구현'), goal=goal)
        self.assertIn('django', captured['system'].casefold())
        self.assertEqual(result['learningSkills'][0]['coreOutcome'], 'FastAPI 대신 Django로 API 구현')
        with self.assertRaisesRegex(llm.LlmError, '(?i)django'):
            self.option(answer('Django 대신 FastAPI로 API 구현'), goal=goal)

    def test_generation_path_handles_unadopted_candidate_and_denied_requirements(self):
        def answer(outcome):
            return target(coreOutcome=outcome, coreCriteria=['응답 코드 확인'])
        for outcome in ('Django는 도입하지 않음', 'FastAPI로 REST API 구현. 후보 기술 목록 (Django)'):
            with self.subTest(outcome=outcome), self.assertRaisesRegex(llm.LlmError, '(?i)django'):
                self.option(answer(outcome))
        result, _ = self.option(answer('FastAPI로 REST API 구현'), goal='Django는 필수까지는 아닙니다')
        self.assertEqual(result['learningSkills'][0]['coreOutcome'], 'FastAPI로 REST API 구현')

    PAIRED_CASES = (
        # (사용자 요구, 핵심 결과, 통과 여부)
        ('Django는 필수까지는 아닙니다', 'FastAPI로 REST API 구현', True),
        ('Django가 필수라는 뜻은 아니에요', 'FastAPI로 REST API 구현', True),
        ('Django가 필수라는 뜻이에요', 'FastAPI로 REST API 구현', False),
        ('Django를 반드시 사용해 중복 저장을 허용하지 않습니다', 'FastAPI로 REST API 구현', False),
        ('Django 사용 필수: 중복 저장은 허용하지 않습니다', 'FastAPI로 REST API 구현', False),
        ('Django 사용 필수, 중복 저장은 허용하지 않습니다', 'FastAPI로 REST API 구현', False),
        ('Django 사용 필수', 'Django로 공개 API 구현', True),
        ('Django 사용 필수', 'Django는 제외하고 FastAPI로 공개 API 구현', False),
        ('Django 사용 필수', 'Django로 관리자 API는 제외하고 공개 API 구현', True),
        ('Django 사용 필수', 'Django로 관리자 API는 제외하고 FastAPI로 공개 API 구현', False),
        ('Django 사용 필수', 'Django API 구현 (Redis는 후속 학습)', True),
        ('Django 사용 필수', 'Django API 구현 (후속 학습)', False),
        ('Django 사용 필수', 'Django (선택 사항)로 API 구현', False),
        ('Python3.9 사용 필수', 'Python3.9로 로그 파서 구현', True),
        ('Python3.14 사용 필수', 'Python3.14로 로그 파서 구현', True),
        ('Python3.14 사용 필수', 'Rust로 로그 파서 구현', False),
        ('Django 또는 FastAPI 중 하나 필수', 'Django로 공개 API 구현', True),
        ('Django 또는 FastAPI 중 하나 필수', 'FastAPI로 공개 API 구현', True),
        ('Django 또는 FastAPI 중 하나 필수', 'Flask로 공개 API 구현', False),
        ('Django와 FastAPI 중 하나 필수', 'FastAPI로 공개 API 구현', True),
        ('Django와 FastAPI 중 하나 필수', 'Flask로 공개 API 구현', False),
        ('반드시 Django와 FastAPI 중 하나 사용', 'FastAPI로 공개 API 구현', True),
        ('Django 또는 FastAPI 중 하나 필수는 아닙니다', 'Flask로 공개 API 구현', True),
        ('Django 또는 FastAPI 중 하나 필수, Redis 필수', 'FastAPI로 공개 API 구현', False),
        ('Django 또는 FastAPI 중 하나와 Redis 필수', 'FastAPI로 공개 API 구현', False),
        ('Django와 FastAPI 모두 필수', 'FastAPI로 공개 API 구현', False),
        ('Django와 FastAPI 모두 필수', 'Django와 FastAPI로 공개 API 구현', True),
        ('Django와 FastAPI 모두 필수는 아닙니다', 'Flask로 공개 API 구현', True),
        ('세션 또는 Redis 중 하나 필수', '세션 기반 로그인 구현', True),
        ('must use one of Django or FastAPI', 'FastAPI로 공개 API 구현', True),
        ('must use one of Django or FastAPI', 'Flask로 공개 API 구현', False),
        ('Django and FastAPI are required', 'Flask로 공개 API 구현', False),
        ('Django and FastAPI are required', 'Django와 FastAPI로 공개 API 구현', True),
        ('Neither Django nor FastAPI is required', 'Flask로 공개 API 구현', True),
        ('Django is required, neither Redis nor Flask is required', 'FastAPI로 공개 API 구현', False),
        ('Django is required, neither Redis nor Flask is required', 'Django로 공개 API 구현', True),
        ('그러나 Django 필수', 'Flask로 공개 API 구현', False),
        ('언제나 Django 필수', 'Flask로 공개 API 구현', False),
    )

    def test_words_before_a_requirement_do_not_cancel_it(self):
        # 앞 낱말의 끝 글자를 연결 표현으로 읽어 필수 요구를 지우면 안 된다.
        for word in ('그러나', '언제나', '누구나', '얼마나', '어디나', '하나', '캐시나', '분석 결과', '테스트 통과', '이번에는', '또는', '이나'):
            for template in ('{} Django 필수', '{} Django is required', '{} 반드시 Django 사용', 'Python 필수, {} Django 필수'):
                goal = template.format(word)
                with self.subTest(goal=goal):
                    self.assertIn(frozenset({'django'}), _requirement_groups({'goal': goal}))

    def test_neither_only_cancels_the_list_right_after_it(self):
        self.assertEqual(_requirement_groups({'goal': 'Django is required, neither Redis nor Flask is required'}), {frozenset({'django'})})
        self.assertEqual(_requirement_groups({'goal': 'Python 필수, neither Django 필수'}), {frozenset({'python'})})
        self.assertEqual(_requirement_groups({'goal': 'Django 필수, neither'}), {frozenset({'django'})})

    def test_quantity_words_decide_alternatives_and_obligations(self):
        one, both = {frozenset({'django', 'fastapi'})}, {frozenset({'django'}), frozenset({'fastapi'})}
        cases = (
            (one, ('Django 또는 FastAPI 필수', 'Django 또는 FastAPI 중 하나는 필수', 'Django 또는 FastAPI 중 하나를 사용해야 합니다',
                  'Django 또는 FastAPI 둘 중 하나 필수', 'Django 또는 FastAPI 가운데 하나 필수', 'Django 또는 FastAPI 중 최소 하나 필수',
                  'Django 또는 FastAPI 중 1개 이상 필수', 'Django 또는 FastAPI 중 택1 필수', 'Django 또는 FastAPI 중 선택 필수',
                  'Django, FastAPI 중 하나 필수', 'Django/FastAPI 중 하나 필수', 'Django·FastAPI 택1 필수', '필수: Django, FastAPI 중 하나',
                  'Either Django or FastAPI is required', 'must use at least one of Django or FastAPI', '프로젝트는 Django, FastAPI 중 하나 필수',
                  'Python 사용, Django 또는 FastAPI 중 하나 필수', '분석 결과 Django 또는 FastAPI 중 하나 필수',
                  'Django 혹은 FastAPI 필수', 'Django 아니면 FastAPI 중 하나 필수')),
            (both, ('Django와 FastAPI 필수', 'Django와 FastAPI 모두 필수', 'Django, FastAPI 둘 다 필수', 'Django와 FastAPI는 전부 필수',
                    '반드시 Django와 FastAPI 모두 사용', 'Both Django and FastAPI are required', 'Django and FastAPI both required')),
            (set(), ('Django 또는 FastAPI 중 하나 사용', 'Django 또는 FastAPI 중 하나는 선택', 'Django 또는 FastAPI 중 선택 사항',
                     'Django 또는 FastAPI 중 어느 쪽도 필수는 아니에요', 'Django 또는 FastAPI 중 하나가 필수라는 뜻은 아니에요',
                     'Django와 FastAPI 둘 다 필수까지는 아닙니다', 'Django and FastAPI are not required',
                     # 대안을 전부 읽지 못하면 남은 기술의 단독 의무로 단정하지 않는다.
                     'REST 또는 GraphQL 중 하나 필수', 'REST, GraphQL 중 하나 필수', 'REST나 GraphQL 필수', '세션 또는 Redis 필수', '세션 혹은 Redis 필수',
                     '세션이나 Redis 필수', '세션, Redis 중 하나 필수', '세션과 Redis 중 하나 필수', '캐시나 Redis 중 하나 필수',
                     'Django 또는 세션 중 하나 필수', 'Django 중급 필수', 'Django 전부터 필수', 'Django 모두의 필수')),
        )
        for expected, goals in cases:
            for goal in goals:
                with self.subTest(goal=goal):
                    self.assertEqual(_requirement_groups({'goal': goal}), expected)
        self.assertEqual(_requirement_groups({'goal': 'Django 또는 FastAPI 중 하나와 Redis 또는 Flask 중 하나 필수'}),
                         {frozenset({'django', 'fastapi'}), frozenset({'redis', 'flask'})})

    def test_chosen_requirement_reaches_the_model_as_an_alternative(self):
        _, captured = self.option(target('FastAPI'), goal='Django와 FastAPI 중 하나 필수')
        self.assertIn('(django 또는 fastapi 중 하나)', captured['system'].casefold())

    @staticmethod
    def paired_core(outcome):
        return target(coreOutcome=outcome, coreCriteria=['응답 코드 확인'])

    def test_paired_cases_on_generation_path(self):
        for goal, outcome, passes in self.PAIRED_CASES:
            with self.subTest(goal=goal, outcome=outcome):
                if passes:
                    result, _ = self.option(self.paired_core(outcome), goal=goal)
                    self.assertEqual(result['learningSkills'][0]['coreOutcome'], outcome)
                else:
                    with self.assertRaises(llm.LlmError):
                        self.option(self.paired_core(outcome), goal=goal)

    def test_paired_cases_on_course_transition_revision_path(self):
        helper = revision_cases.CourseTransitionTargetsTests()
        for goal, outcome, passes in self.PAIRED_CASES:
            with self.subTest(goal=goal, outcome=outcome):
                inp = helper.revision_input('A3', 'A2', names=[WEB])
                inp['handoff']['goal'] = goal
                if passes:
                    result, _, _ = helper.revise_input(inp, [self.paired_core(outcome)])
                    self.assertEqual(result['learningSkills'][0]['coreOutcome'], outcome)
                else:
                    with self.assertRaises(llm.LlmError):
                        helper.revise_input(inp, [self.paired_core(outcome)])

    def test_oversized_request_is_rejected_before_model_generation(self):
        with self.assertRaises(ApiError) as caught:
            self.option(target(), goal='Django 필수', request={'wish': '가' * MAX_REQUIREMENT_CHARS})
        self.assertEqual((caught.exception.status, caught.exception.code), (422, 'CRASH_REQUIREMENTS_TOO_LONG'))

    def test_regeneration_does_not_replace_previous_plan_when_new_requirement_missing(self):
        previous = {'id': 'A2', 'acts': [], 'learningSkills': [target('Django')], 'version': 'old'}
        before = deepcopy(previous)
        with self.assertRaisesRegex(llm.LlmError, '(?i)django'):
            self.option(target(), previous=previous)
        self.assertEqual(previous, before)

    def test_regeneration_wish_is_user_requirement(self):
        with self.assertRaisesRegex(llm.LlmError, '(?i)django'):
            self.option(target(), goal='웹 API 구현', request={'wish': 'Django 사용 필수'})

    def test_mock_generation_cannot_silently_drop_mandatory_technology(self):
        with self.assertRaisesRegex(llm.LlmError, '(?i)django'):
            self.option(target(), mock=True)

    def test_mock_generation_treats_same_denials_alike(self):
        for goal in ('Django는 필수까지는 아닙니다', 'Django가 필수라는 뜻은 아니에요'):
            with self.subTest(goal=goal):
                self.option(target(), goal=goal, mock=True)
        with self.assertRaisesRegex(llm.LlmError, '(?i)django'):
            self.option(target(), goal='Django가 필수라는 뜻이에요', mock=True)

    def test_optional_comparison_does_not_become_required(self):
        result, _ = self.option(target(), goal='FastAPI 구현 후 Django 비교')
        self.assertEqual(result['learningSkills'][0]['coreOutcome'], 'FastAPI REST API 구현')

    def test_course_transition_rejects_required_technology_shifted_to_follow_up(self):
        helper = revision_cases.CourseTransitionTargetsTests()
        inp = helper.revision_input('A3', 'A2', names=[WEB])
        inp['handoff']['goal'] = 'Django 사용 필수'
        before = deepcopy(inp)
        with self.assertRaisesRegex(llm.LlmError, '(?i)django'):
            helper.revise_input(inp, [target()])
        self.assertEqual(inp, before)

    def test_course_transition_keeps_valid_core_and_completed_activity(self):
        helper = revision_cases.CourseTransitionTargetsTests()
        inp = helper.revision_input('A3', 'A2', names=[WEB])
        inp['handoff']['goal'] = 'Django 사용 필수'
        result, _, plan = helper.revise_input(inp, [target('Django')])
        self.assertEqual(result['learningSkills'][0]['coreOutcome'], 'Django REST API 구현')
        self.assertEqual(result['acts'][0]['key'], plan['acts'][0]['id'])
        self.assertTrue(plan['acts'][0]['done'])

    def test_same_course_revision_checks_final_saved_core_not_discarded_model_targets(self):
        helper = revision_cases.CourseTransitionTargetsTests()
        inp = helper.revision_input('A2', 'A2', names=[WEB])
        inp['handoff']['goal'] = '웹 API 구현'
        inp['request'] = 'Django 사용 필수'
        inp['plan']['def']['learningSkills'] = [target()]
        before = deepcopy(inp)
        with self.assertRaises(ApiError) as caught:
            helper.revise_input(inp, [target('Django')])
        self.assertEqual((caught.exception.status, caught.exception.code), (422, 'CRASH_CORE_REQUIREMENT_CONFLICT'))
        self.assertIn('django', caught.exception.extra['cause'].casefold())
        self.assertEqual(inp, before)

    def test_revision_constraints_from_user_notes_cannot_bypass_validation(self):
        helper = revision_cases.CourseTransitionTargetsTests()
        inp = helper.revision_input('A3', 'A2', names=[WEB])
        inp['handoff']['goal'] = '웹 API 구현'
        # plans.revise_start는 기타 제약 값을 userNotes와 changes.constraints에 넣는다.
        inp['handoff']['userNotes'] = ['Django 사용 필수']
        inp['changes']['constraints'] = 'Django 사용 필수'
        before = deepcopy(inp)
        with self.assertRaisesRegex(llm.LlmError, '(?i)django'):
            helper.revise_input(inp, [target()])
        self.assertEqual(inp, before)
        result, captured, _ = helper.revise_input(inp, [target('Django')])
        self.assertIn('django', captured['system'].casefold())
        self.assertIn('Django', result['learningSkills'][0]['coreOutcome'])

    def test_legacy_initialization_validates_before_saving(self):
        option = {'id': 'A2', 'name': 'Crash', 'acts': [{'title': '기존 활동'}]}
        wrapper = {'draft': {'gen': {'options': {'A2': option}}}}
        saved = {'generationId': 'g', 'selection': {'skills': [{'name': WEB}]},
                 'project': {'goal': 'Django 사용 필수'}}
        before = deepcopy(option)
        with patch.object(course_skills, 'generation_guard', side_effect=lambda *args: nullcontext()), \
             patch.object(db, 'tx', side_effect=lambda: nullcontext(Mock())), \
             patch.object(preassessment, 'recommendation_context', return_value=saved), \
             patch.object(drafts, '_row', return_value={'draft_choices': wrapper}), \
             patch.object(drafts, '_wrap', side_effect=lambda value: value), \
             patch.object(drafts, '_mutate') as mutate, \
             patch.object(runtime, 'context', return_value=SimpleNamespace(live=True)), \
             patch.object(runtime, 'llm_json', return_value={'learningSkills': [target()]}):
            with self.assertRaisesRegex(ApiError, '(?i)django'):
                course_skills.initialize(1, 'project', 'A2')
            mutate.assert_not_called()
        self.assertEqual(option, before)

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

    def test_requirements_can_be_covered_across_multiple_skills(self):
        rows = [target('Django'), target('PostgreSQL', name='SQL')]
        before = deepcopy(rows)
        validate_core_requirements(rows, {'goal': '필수 기술: Django, PostgreSQL'})
        self.assertEqual(rows, before)
        with self.assertRaisesRegex(ValueError, '(?i)postgresql'):
            validate_core_requirements(rows[:1], {'goal': '필수 기술: Django, PostgreSQL'})

    def test_requirement_sources_exclude_profile_and_model_recommendations(self):
        handoff = {'goal': 'FastAPI 구현 후 Django 비교',
                   'profile': {'workDesc': 'Django 사용 필수'},
                   'skillDetails': [{'application': 'Django 사용 필수'}]}
        self.assertEqual(required_technologies(handoff), set())
        self.assertEqual(required_technologies(handoff, {'wish': '장고를 반드시 사용'}), {'django'})


if __name__ == '__main__':
    unittest.main()
