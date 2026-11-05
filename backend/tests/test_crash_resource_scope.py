"""Crash 검색과 후보 판정에서 핵심 학습 범위가 일치하는지 검사한다."""
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

from app.agents.resource_recommendations import recommend_resources, validate_choices
from app.services import crash_courses, resource_evidence, resource_rag
from test_recommendation_suitability import WEB, course


class CrashResourceScopeTests(unittest.TestCase):
    def setUp(self):
        self.project = {
            'goal': 'FastAPI와 Django REST API 구현',
            'projectSummary': 'Django followup_summary',
            'desiredCompetencies': 'Django followup_competency',
            'learnerKnowledge': {'techStack': ['Django']},
        }
        self.skill = {
            'name': WEB,
            'application': 'FastAPI 구현 후 Django followup_application',
            'coreOutcome': 'FastAPI API 구현',
            'coreCriteria': ['FastAPI REST API 구현과 테스트'],
            'followUpScope': ['Django REST API 비교'],
        }
        self.selection = {'skills': [self.skill]}
        self.option = {
            'id': 'A2',
            'reason': 'Django followup_reason',
            'scope': 'FastAPI 구현 후 Django followup_scope',
            'learningSkills': [self.skill],
        }
        self.short = course('short', ['FastAPI REST API 구현 실습'], skills=[WEB], hours=2)
        self.long = course('long', ['FastAPI REST API 구현 실습', 'Django REST API 구현 실습'],
                           skills=[WEB], hours=10)
        self.django = course('django', ['Django REST API 구현 실습'], skills=[WEB], hours=1)

    def test_retrieval_and_recommendation_choose_two_hours_for_same_core(self):
        original = deepcopy((self.project, self.selection, self.option))
        items = {row['id']: row for row in (self.long, self.django, self.short)}
        embed = Mock(return_value=[[1.0] + [0.0] * (resource_rag.DIMENSIONS - 1)])
        # 긴 강좌가 벡터 순위에서 앞서도 같은 핵심을 다루는 짧은 강좌가 기본안이다.
        search = Mock(return_value=[{'resource_id': key, 'similarity': score}
                                    for key, score in [('long', .92), ('django', .88), ('short', .82)]])
        pools, _ = resource_rag.retrieve(self.project, self.selection, items, self.option,
                                         embed=embed, search=search)
        embed.assert_called_once()
        query, = embed.call_args.args[0]
        self.assertNotIn('django', query.casefold())
        self.assertNotIn('followup', query.casefold())
        self.assertEqual(json.loads(query), {'course': {'id': 'A2'}, 'coreOutcome': self.skill['coreOutcome'],
                                             'coreCriteria': self.skill['coreCriteria']})
        self.assertEqual(pools[0]['courses'][0]['id'], 'short')

        generate = Mock(return_value={'skills': [{'name': WEB, 'books': [],
                                                   'courses': [{'id': 'long'}, {'id': 'short'}, {'id': 'django'}]}]})
        result = recommend_resources(self.project, self.selection, items, generate, course=self.option,
                                     retrieved_pools=pools)
        payload = generate.call_args.args[1]
        profiles = {row['title']: row['learningEvidence'] for row in payload['skills'][0]['courses']}
        self.assertEqual(profiles['short']['requiredStack'], ['fastapi'])
        self.assertEqual(profiles['short']['missingStack'], [])
        self.assertFalse(profiles['django']['suitable'])
        self.assertEqual(profiles['django']['missingStack'], ['fastapi'])
        self.assertEqual(payload['crashStudyPlan']['uniqueHours'], 2)
        self.assertEqual(result['skills'][0]['selectedCourse'], 'short')
        self.assertEqual(payload['project']['goal'], original[0]['goal'])
        self.assertEqual((self.project, self.selection, self.option), original)

    def test_unsuitable_model_only_choice_leaves_course_unselected(self):
        items = {row['id']: row for row in (self.short, self.long, self.django)}
        pools = [{'name': WEB, 'courses': list(items.values()), 'books': []}]
        raw = {'skills': [{'name': WEB, 'courses': [{'id': 'django'}], 'books': []}]}
        result = recommend_resources(self.project, self.selection, items, lambda *_: raw,
                                     course=self.option, retrieved_pools=pools)
        row, = result['skills']
        self.assertEqual(row['courses'], [])
        self.assertIsNone(row['selectedCourse'])
        self.assertIn(row['courseDiagnostic']['reason'], ('stack_mismatch', 'insufficient_evidence'))
        validate_choices(result, {WEB: {'course': None, 'books': []}})

    def test_core_security_stage_and_explicit_stack_still_required(self):
        self.skill['coreCriteria'] = ['FastAPI 보안 개념과 권한 경계를 검증']
        secured = course('secured', ['FastAPI 권한 경계 검증 실습'], skills=[WEB], hours=6)
        wrong_stack = course('wrong', ['Django 권한 경계 검증 실습'], skills=[WEB], hours=1)
        profiles = {row['id']: resource_evidence.facts(row, self.project, self.selection)
                    for row in (self.short, wrong_stack, secured)}
        short_profile = profiles['short']['suitability'][WEB]
        self.assertEqual(short_profile['requiredStage'], 'security')
        self.assertFalse(short_profile['suitable'])
        self.assertEqual(profiles['wrong']['suitability'][WEB]['missingStack'], ['fastapi'])
        self.assertTrue(profiles['secured']['suitability'][WEB]['suitable'])
        pools = [{'name': WEB, 'courses': [self.short, wrong_stack, secured]}]
        chosen = crash_courses.shortest_bundle(pools, self.project, self.selection, profiles)
        self.assertEqual(chosen[WEB]['id'], 'secured')

    def test_core_implementation_and_security_can_be_taught_in_separate_units(self):
        self.skill['coreOutcome'] = 'FastAPI CRUD API'
        self.skill['coreCriteria'] = ['권한 테스트 통과']
        security_unit = 'JWT 권한 경계 검증 실습'
        complete = course('complete', ['FastAPI REST API 구현 실습', security_unit],
                          skills=[WEB], hours=2)
        longer = course('longer', ['FastAPI 권한 경계 검증 실습'], skills=[WEB], hours=10)
        introduction = course('intro', ['FastAPI REST API 구현 개요', security_unit], skills=[WEB])
        prerequisite = course('prerequisite', [security_unit], skills=[WEB],
                              content='선수지식: FastAPI REST API 구현 실습')
        prerequisite['curriculum']['items'].insert(
            0, {'section': '선수지식', 'title': 'FastAPI REST API 구현 실습'})
        no_security_practice = course('no-security', ['FastAPI REST API 구현 실습', 'JWT 권한 경계 개요'],
                                      skills=[WEB])
        rows = [complete, longer, introduction, prerequisite, no_security_practice]
        cache = {row['id']: resource_evidence.facts(row, self.project, self.selection) for row in rows}
        self.assertTrue(resource_evidence.suitable(cache['complete'], WEB))
        for key in ('intro', 'prerequisite', 'no-security'):
            with self.subTest(key=key):
                self.assertFalse(resource_evidence.suitable(cache[key], WEB))
        chosen = crash_courses.shortest_bundle([{'name': WEB, 'courses': rows}],
                                               self.project, self.selection, cache)
        self.assertEqual(chosen[WEB]['id'], 'complete')

        # 보안 기준 자체가 특정 기술을 명시하면 구현 차시만으로 그 조건을 대신하지 않는다.
        self.skill['coreCriteria'][0] = 'FastAPI에서 JWT 권한 경계 검증'
        profile = resource_evidence.facts(complete, self.project, self.selection)['suitability'][WEB]
        self.assertEqual(profile['missingStack'], ['fastapi'])
        self.assertFalse(profile['suitable'])

    def test_core_quality_kept_and_deferred_dbt_targets_ignored(self):
        skill = {'name': 'ETL', 'application': 'dbt 백필 재처리와 배포',
                 'coreOutcome': 'dbt 증분 모델', 'coreCriteria': ['dbt 증분 모델 실행과 품질 테스트'],
                 'followUpScope': ['백필 재처리와 배포']}
        project = {'goal': 'dbt 백필 재처리와 배포'}
        partial = course('partial', ['dbt 증분 모델 구현 실습'], skills=['ETL'], hours=1)
        core = course('core', ['dbt 증분 모델 구현 실습', 'dbt 데이터 품질 테스트 실습'], skills=['ETL'])
        selection = {'skills': [skill]}
        cache = {row['id']: resource_evidence.facts(row, project, selection) for row in (partial, core)}
        self.assertEqual(cache['partial']['suitability']['ETL']['requiredStage'], 'build')
        self.assertEqual(resource_evidence.target_gaps(cache['partial'], 'ETL'), ['dbt 품질 테스트'])
        self.assertEqual(resource_evidence.target_gaps(cache['core'], 'ETL'), [])
        chosen = crash_courses.shortest_bundle([{'name': 'ETL', 'courses': [partial, core]}],
                                               project, selection, cache)
        self.assertEqual(chosen['ETL']['id'], 'core')

    def test_global_goal_does_not_override_core_stage_or_scope(self):
        name = 'MLOps & 모델 서빙'
        skill = {'name': name, 'application': '모델 배포·모니터링',
                 'coreOutcome': '모델 버전 관리 설계', 'coreCriteria': ['버전 관리 아키텍처 비교'],
                 'followUpScope': ['모니터링과 배포']}
        row = course('design', ['MLOps 모델 버전 관리 아키텍처 설계'], skills=[name])
        profile = resource_evidence.facts(row, {'goal': '모델 배포'}, {'skills': [skill]})['suitability'][name]
        self.assertEqual(profile['requiredStage'], 'design')
        self.assertTrue(profile['suitable'])

        skill = {'name': 'Python', 'application': 'Python 로그 데이터 분석',
                 'coreOutcome': 'Python API 구현', 'coreCriteria': ['Python으로 API 호출 구현'],
                 'followUpScope': ['로그 데이터 분석']}
        row = course('api', ['Python REST API 연동 실습'], skills=['Python'])
        info = resource_evidence.facts(row, {'goal': 'Python 로그 데이터 분석'}, {'skills': [skill]})
        self.assertTrue(info['scopeEvidence']['Python'])
        self.assertTrue(resource_evidence.suitable(info, 'Python'))

    def test_free_challenge_and_legacy_crash_keep_full_scope(self):
        skill = {'name': WEB, 'application': 'FastAPI와 Django REST API 구현'}
        for track in ('A1', 'A2', 'A3'):
            with self.subTest(track=track):
                query = json.loads(resource_rag.query_text(self.project, skill, {'id': track, 'scope': 'Django 구현'}))
                self.assertEqual(query['projectGoal'], self.project['goal'])
                self.assertEqual(query['projectSummary'], self.project['projectSummary'])
                self.assertEqual(query['application'], skill['application'])
                self.assertEqual(query['course']['scope'], 'Django 구현')
                self.assertNotIn('coreCriteria', query)
        profiles = resource_evidence.facts(self.short, self.project, {'skills': [skill]})['suitability']
        self.assertEqual(profiles[WEB]['missingStack'], ['django'])
