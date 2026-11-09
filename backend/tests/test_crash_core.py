"""Crash 핵심 완료 기준: 계획 → 자료 검색·판정 → 과제·역량 요약이 같은 기준을 공유한다. 모델·DB 호출 없음."""
import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from app import track_policy
from app.agents import roadmap
from app.agents.roadmap_generation import generation
from app.agents.roadmap_revision import revision
from app.agents.resource_instructions import instructions as resource_instructions
from app.errors import cause
from app.services import activity_selection as activities, course_skills, crash_courses as crash
from app.services.activity_instructions import instructions as task_instructions
from app.services.course_recommendations import scope_view
from app.services.learning_outcomes import instructions as summary_instructions
from app.services.resource_rag import query_text

ETL = 'ETL & 데이터 파이프라인'


def target(**changes):
    return dict({'name': ETL, 'application': 'dbt로 증분 모델과 품질 테스트를 구현하고 백필 절차를 정리',
                 'coreOutcome': '주문 테이블 dbt 증분 모델 1개', 'coreCriteria': ['dbt 증분 모델 실행 결과 확인'],
                 'followUpScope': ['dbt 품질 테스트 확장', '재처리·백필 절차']}, **changes)


def course(key, hours, title, items):
    return {'id': key, 'type': 'course', 'usable': True, 'skills': [ETL], 'hours': hours, 'timeStatus': 'confirmed',
            'estimated': [], 'cost': 0, 'title': title, 'content': f'학습목표\n{title}',
            'curriculum': {'items': items}, 'retrievalScore': .8}


class CrashCoreTests(unittest.TestCase):
    def test_guidance_is_crash_only_and_shared_by_every_stage(self):
        for stage in ('plan', 'resources', 'tasks', 'summary'):
            self.assertIn(track_policy.CRASH_CORE_MARKER, track_policy.crash_guidance('A2', stage))
            self.assertEqual(track_policy.crash_guidance('A1', stage), '')
            self.assertEqual(track_policy.crash_guidance('A3', stage), '')
            self.assertEqual(track_policy.course_guidance('A3', stage), track_policy.challenge_guidance('A3', stage))
        for text in (resource_instructions({'id': 'A2'}), task_instructions('A2'), summary_instructions('A2'),
                     generation('A2'), revision('A2')):
            self.assertEqual(text.count(track_policy.CRASH_CORE_MARKER), 1)
        for text in (resource_instructions({'id': 'A1'}), task_instructions('A3'), generation('A3'), revision('A1')):
            self.assertNotIn(track_policy.CRASH_CORE_MARKER, text)
        schema = json.loads(generation('A2').split('JSON 형식 예: ', 1)[1])
        self.assertTrue({'coreOutcome', 'coreCriteria', 'followUpScope'} <= set(schema['learningSkills'][0]))

    def test_plan_validation_requires_core_criteria_but_reads_previous_crash_plans(self):
        rows = course_skills.validate_recommendations([target()], {ETL}, 'A2', require_depth=True)
        self.assertEqual(rows[0]['coreCriteria'], ['dbt 증분 모델 실행 결과 확인'])
        self.assertEqual(rows[0]['followUpScope'], ['dbt 품질 테스트 확장', '재처리·백필 절차'])
        legacy = {'name': ETL, 'application': '증분 모델'}
        self.assertEqual(course_skills.validate_recommendations([legacy], {ETL}, 'A2'), [legacy])
        self.assertEqual(course_skills.validate_recommendations([target(followUpScope=None)], {ETL}, 'A2',
                                                                require_depth=True)[0]['followUpScope'], [])
        for bad in (legacy, target(coreOutcome=' '), target(coreCriteria=[]), target(coreCriteria=['a', 'b', 'c', 'd']),
                    target(coreCriteria=['같은 기준', '같은  기준']), target(followUpScope=['1', '2', '3', '4']),
                    target(followUpScope='후속')):
            with self.subTest(row=bad), self.assertRaises(ValueError) as error:
                course_skills.validate_recommendations([bad], {ETL}, 'A2', require_depth=True)
            self.assertEqual(cause(str(error.exception))['kind'], 'format')

    def test_integrated_prompt_also_requests_learning_skills_for_required_legacy_crash(self):
        def system_for(handoff):
            captured = {}
            def model(ctx, value, payload, **kw):
                captured['system'] = value
                return {'acts': [], 'learningSkills': [target(coreOutcome='Django로 ETL API 구현')]}
            with patch.object(roadmap, '_sys', return_value='[통합 생성 계약 roadmap-generation/v1]\n계약'), \
                    patch.object(roadmap.catalog, 'skill_names', return_value=[ETL]), \
                    patch.object(roadmap, '_catalog_payload', side_effect=lambda pid, payload, *args: deepcopy(payload)), \
                    patch.object(roadmap.rt, 'llm_json', side_effect=model), \
                    patch.object(roadmap, '_validate_learning_acts'), \
                    patch.object(roadmap, 'finish_option', return_value={'acts': []}), \
                    patch.object(roadmap.rt, 'run', side_effect=lambda ctx, name, task, inp, mock, api, **kw: api(None)):
                roadmap.option(SimpleNamespace(mode='openai'), {'pid': 'A2', 'handoff': handoff})
            return captured['system']
        self.assertIn('[구형 Crash 필수 기술 응답 계약]', system_for({'goal': 'Django 사용 필수'}))
        self.assertNotIn('[구형 Crash 필수 기술 응답 계약]', system_for({'goal': 'ETL 학습'}))

    def test_previously_installed_integrated_prompt_receives_crash_contract_once(self):
        handoff = {'goal': 'dbt 증분 모델', 'assessmentGenerationId': 'g', 'selectedSkillsFixed': True,
                   'courseSkillSelection': True, 'skillNames': [ETL], 'skillOrder': [ETL],
                   'skillDetails': [{'name': ETL, 'application': target()['application']}]}
        def run(system, answer):
            captured = {}
            def model(ctx, value, payload, **kw):
                captured['system'] = value
                return {'acts': [], 'learningSkills': [answer]}
            with patch.object(roadmap, '_sys', return_value=system), \
                    patch.object(roadmap.catalog, 'skill_names', return_value=[ETL]), \
                    patch.object(roadmap, '_catalog_payload', side_effect=lambda pid, payload, *args: deepcopy(payload)), \
                    patch.object(roadmap.rt, 'llm_json', side_effect=model), \
                    patch.object(roadmap, '_validate_learning_acts'), \
                    patch.object(roadmap, 'finish_option', return_value={'acts': []}), \
                    patch.object(roadmap.rt, 'run', side_effect=lambda ctx, name, task, inp, mock, api, **kw: api(None)):
                result = roadmap.option(SimpleNamespace(mode='openai'), {'pid': 'A2', 'handoff': handoff})
            return result, captured['system']
        old = '[통합 생성 계약 roadmap-generation/v1]\n이전 Crash 계약'
        result, system = run(old, target())
        self.assertEqual(system.count(track_policy.CRASH_CORE_MARKER), 1)
        # 계획의 application은 사용자가 확정한 값으로 유지하고 핵심 기준은 모델 응답에서 가져온다.
        self.assertEqual(result['learningSkills'][0]['application'], target()['application'])
        self.assertEqual(result['learningSkills'][0]['coreCriteria'], target()['coreCriteria'])
        _, system = run(generation('A2'), target())
        self.assertEqual(system.count(track_policy.CRASH_CORE_MARKER), 1)
        with self.assertRaises(roadmap.llm.LlmError):
            run(old, {'name': ETL, 'application': '증분 모델'})

    def test_core_criteria_reach_resource_search_and_tasks_without_follow_up_scope(self):
        rows = course_skills.validate_recommendations([target()], {ETL}, 'A2', require_depth=True)
        saved = {'generationId': 'g', 'project': {'selectedSkills': [ETL]},
                 'selection': {'skills': [{'name': ETL, 'application': target()['application']}]}}
        skill = scope_view(saved, 'A2', {'learningSkills': rows})['selection']['skills'][0]
        self.assertEqual(skill, target())
        query = json.loads(query_text({'goal': 'dbt'}, skill, {'id': 'A2'}))
        self.assertEqual(query['coreCriteria'], target()['coreCriteria'])
        self.assertNotIn('followUpScope', query)
        self.assertNotIn('coreCriteria', json.loads(query_text({'goal': 'dbt'}, skill, {'id': 'A1'})))
        task_saved = {'generationId': 'g', 'project': {'goal': 'dbt'}, 'recommendations': {'id': 'r'},
                      'selection': {'skills': [skill]}, 'skillOrder': [ETL],
                      'resourceChoices': {ETL: {'course': None, 'books': []}}}
        draft = {'chosen': 'A2', 'handoff': {'key': 'h'}, 'gen': {'options': {'A2': {'id': 'A2', 'learningSkills': rows}}}}
        with patch.object(activities.catalog, 'items', return_value={}):
            _, payload = activities.learning_context(task_saved, draft)
        self.assertEqual(payload['skillTargets'][ETL]['coreCriteria'], target()['coreCriteria'])

    def test_crash_default_meets_core_criteria_and_ignores_deferred_targets(self):
        project = {'goal': 'dbt 기반 주문 파이프라인'}
        short = course('short', 2, 'dbt 증분 모델', [{'section': 'dbt 증분', 'title': 'dbt 증분 모델 구현 실습'}])
        full = course('full', 9, 'dbt 실무', [{'section': 'dbt 증분', 'title': 'dbt 증분 모델 구현 실습'},
                                             {'section': 'dbt 테스트', 'title': 'dbt 테스트로 품질 검증 실습'},
                                             {'section': 'dbt 백필', 'title': 'dbt 백필 재처리 실습'}])
        intro = course('intro', 1, 'dbt 소개', [{'section': 'dbt 시작', 'title': 'dbt 설치 실습'}])
        pools = [{'name': ETL, 'courses': [full, short, intro]}]
        refs = {'full': 'S1-C1', 'short': 'S1-C2', 'intro': 'S1-C3'}
        core = {'skills': [target()]}
        cache = {}
        plan = crash.study_plan(pools, project, core, refs, cache=cache)
        # 후속 학습으로 넘긴 품질 테스트·백필은 요구하지 않는다. 핵심 기준을 충족하는 짧은 강좌가 기본안이다.
        self.assertEqual(plan['skills'][0]['key'], 'S1-C2')
        self.assertEqual(plan['uniqueHours'], 2)
        self.assertEqual(crash.target_gaps(cache['short'], ETL), [])
        self.assertIn('dbt 증분 처리', crash.target_gaps(cache['intro'], ETL))
        self.assertEqual(plan['skills'][0]['singleSwapExtraHours'], {'S1-C1': 7.0})
        # 핵심 기준이 없는 이전 안은 전체 application을 기준으로 판정한다.
        legacy = {'skills': [{'name': ETL, 'application': target()['application']}]}
        legacy_plan = crash.study_plan(pools, project, legacy, refs, cache={})
        self.assertEqual(legacy_plan['skills'][0]['key'], 'S1-C1')


if __name__ == '__main__':
    unittest.main()
