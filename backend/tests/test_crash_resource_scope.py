"""Crash 검색과 후보 판정에서 핵심 학습 범위가 일치하는지 검사한다."""
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

from app.agents.resource_recommendations import RecommendationError, recommend_resources, validate_choices
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
        self.project = {'goal': 'FastAPI로 REST API 구현'}
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
        self.assertNotIn('followup', query.casefold())
        self.assertEqual(json.loads(query)['goal'], self.project['goal'])
        self.assertNotIn('coreCriteria', json.loads(query))
        self.assertEqual(pools[0]['courses'][0]['id'], 'short')

        generate = Mock(return_value={'skills': [{'name': WEB, 'books': [],
                                                   'courses': [{'id': 'long'}, {'id': 'short'}]}]})
        result = recommend_resources(self.project, self.selection, items, generate, course=self.option,
                                     retrieved_pools=pools)
        payload = generate.call_args.args[1]
        profiles = {row['title']: row['learningEvidence'] for row in payload['skills'][0]['courses']}
        self.assertEqual(profiles['short']['requiredStack'], ['fastapi'])
        self.assertEqual(profiles['short']['missingStack'], [])
        self.assertNotIn('django', profiles)
        self.assertEqual(payload['crashStudyPlan']['uniqueHours'], 2)
        self.assertEqual(result['skills'][0]['selectedCourse'], 'short')
        self.assertEqual(payload['project']['goal'], original[0]['goal'])
        self.assertEqual((self.project, self.selection, self.option), original)

    def test_unsuitable_model_only_choice_cannot_reference_a_filtered_course(self):
        items = {row['id']: row for row in (self.short, self.long, self.django)}
        pools = [{'name': WEB, 'courses': list(items.values()), 'books': []}]
        raw = {'skills': [{'name': WEB, 'courses': [{'id': 'django'}], 'books': []}]}
        before = deepcopy((self.project, self.selection, pools))
        with self.assertRaises(RecommendationError):
            recommend_resources(self.project, self.selection, items, lambda *_: raw,
                                course=self.option, retrieved_pools=pools)
        self.assertEqual((self.project, self.selection, pools), before)

    def test_core_replacement_recognizes_only_applied_technology(self):
        self.project['goal'] = 'Django 사용 필수'
        self.skill['coreCriteria'] = ['응답 코드 확인']
        for outcome in ('FastAPI 대신 Django로 REST API 구현',
                        'FastAPI를 쓰지 않고 Django로 REST API 구현',
                        'Django로 REST API 구현 instead of FastAPI',
                        'Django로 REST API 구현 후 FastAPI 비교',
                        'Spring Boot 대신 Django로 REST API 구현',
                        'Django로 오류 없이 REST API 구현'):
            with self.subTest(outcome=outcome):
                self.skill['coreOutcome'] = outcome
                original = deepcopy((self.project, self.selection))
                good = resource_evidence.facts(self.django, self.project, self.selection)
                wrong = resource_evidence.facts(self.short, self.project, self.selection)
                profile = good['suitability'][WEB]
                self.assertEqual(profile['requiredStack'], ['django'])
                self.assertEqual(profile['missingStack'], [])
                self.assertEqual(profile['conflictingStack'], [])
                self.assertTrue(resource_evidence.suitable(good, WEB))
                self.assertFalse(resource_evidence.suitable(wrong, WEB))
                self.assertEqual(wrong['suitability'][WEB]['missingStack'], ['django'])
                self.assertEqual((self.project, self.selection), original)

    def test_replacement_retrieval_payload_and_final_recommendation(self):
        self.project['goal'] = 'Django 사용 필수'
        self.skill.update(coreOutcome='FastAPI 대신 Django로 REST API 구현',
                          coreCriteria=['응답 코드 확인'])
        self.django['hours'] = 5
        self.short['hours'] = 1
        original = deepcopy((self.project, self.selection, self.option))
        items = {row['id']: row for row in (self.short, self.django)}
        embed = Mock(return_value=[[1.0] + [0.0] * (resource_rag.DIMENSIONS - 1)])
        search = Mock(return_value=[{'resource_id': 'short', 'similarity': .95},
                                    {'resource_id': 'django', 'similarity': .8}])
        pools, _ = resource_rag.retrieve(self.project, self.selection, items, self.option,
                                         embed=embed, search=search)
        query, = embed.call_args.args[0]
        self.assertEqual(json.loads(query)['goal'], self.project['goal'])
        self.assertNotIn('coreOutcome', json.loads(query))
        self.assertEqual(pools[0]['courses'][0]['id'], 'django')
        generate = Mock(return_value={'skills': [{'name': WEB, 'books': [],
                                                   'courses': [{'id': 'django'}]}]})
        result = recommend_resources(self.project, self.selection, items, generate, course=self.option,
                                     retrieved_pools=pools)
        payload = generate.call_args.args[1]
        profiles = {row['title']: row['learningEvidence'] for row in payload['skills'][0]['courses']}
        self.assertEqual(profiles['django']['requiredStack'], ['django'])
        self.assertTrue(profiles['django']['suitable'])
        self.assertNotIn('short', profiles)
        self.assertEqual(payload['crashStudyPlan']['uniqueHours'], 5)
        self.assertEqual(result['skills'][0]['selectedCourse'], 'django')
        validate_choices(result, {WEB: {'course': 'django', 'books': []}})

        generate.return_value['skills'][0]['courses'] = [{'id': 'short'}]
        pools = [{'name': WEB, 'courses': list(items.values()), 'books': []}]
        with self.assertRaises(RecommendationError):
            recommend_resources(self.project, self.selection, items, generate, course=self.option,
                                retrieved_pools=pools)
        self.assertEqual((self.project, self.selection, self.option), original)

    def test_core_still_requires_every_applied_framework(self):
        self.skill.update(coreOutcome='FastAPI와 Django REST API 구현', coreCriteria=['응답 코드 확인'])
        for row, suitable in ((self.short, False), (self.django, False), (self.long, True)):
            with self.subTest(course=row['id']):
                info = resource_evidence.facts(row, self.project, self.selection)
                self.assertEqual(info['suitability'][WEB]['requiredStack'], ['django', 'fastapi'])
                self.assertEqual(resource_evidence.suitable(info, WEB), suitable)

    def test_core_criteria_distinguish_comparison_from_implementation(self):
        self.skill['coreOutcome'] = 'Django REST API 구현'
        for criterion, required, suitable in (('FastAPI 비교', ['django'], True),
                                               ('FastAPI REST API 구현', ['django', 'fastapi'], False)):
            with self.subTest(criterion=criterion):
                self.skill['coreCriteria'] = [criterion]
                info = resource_evidence.facts(self.django, self.project, self.selection)
                self.assertEqual(info['suitability'][WEB]['requiredStack'], required)
                self.assertEqual(resource_evidence.suitable(info, WEB), suitable)

    def test_course_stack_reading_uses_the_same_version_conversion(self):
        for text in ('Python3.14로 REST API 구현 실습', 'Python3.9 REST API 구현 실습', 'Python REST API 구현 실습'):
            with self.subTest(text=text):
                self.assertEqual(resource_evidence._core_stack_names([text]), {'python'})

    def test_applied_units_outside_a_verb_list_still_teach_the_required_stack(self):
        for name, stack, text in (
            ('Spring Boot', 'spring', '스프링부트 프로젝트 생성 실습'),
            ('Spring Boot', 'spring', 'Next.js, Spring Boot 기반 웹 서비스를 구현'),
            ('Python', 'python', 'Hands On: Dockerizing Python Flask Application'),
        ):
            with self.subTest(text=text):
                self.skill.update(coreOutcome=f'{name} REST API 구현', coreCriteria=['응답 코드 확인'])
                row = course('good', [text], skills=[WEB])
                profile = resource_evidence.facts(row, {'goal': f'{name} 사용 필수'}, self.selection)['suitability'][WEB]
                self.assertIn(stack, profile['requiredStack'])
                self.assertEqual(profile['missingStack'], [])

    def test_applied_units_and_descriptions_do_not_teach_excluded_or_partial_names(self):
        self.skill.update(coreOutcome='Django REST API 구현', coreCriteria=['응답 코드 확인'])
        for text in ('Django 대신 FastAPI로 REST API 구현',
                     'Django를 쓰지 않고 FastAPI로 REST API 구현',
                     'FastAPI REST API 구현 후 Django 비교',
                     'FastAPI로 구현하고 Django 문서 참고',
                     '냉장고 재고 API 구현', '장고만두 재고 API 구현'):
            for source in ('unit', 'description'):
                with self.subTest(text=text, source=source):
                    row = course('wrong', [text] if source == 'unit' else [], skills=[WEB],
                                 title='Django 비교 과정', content=text if source == 'description' else '')
                    original = deepcopy(row)
                    profile = resource_evidence.facts(row, self.project, self.selection)['suitability'][WEB]
                    self.assertEqual(profile['requiredStack'], ['django'])
                    self.assertEqual(profile['missingStack'], ['django'])
                    self.assertFalse(profile['suitable'])
                    self.assertEqual(row, original)

        for text in ('Django REST API 구현 실습', '장고로만 REST API 구현 실습',
                     'FastAPI 대신 Django로 REST API 구현', 'Spring Boot 대신 Django로 REST API 구현',
                     'Django REST API 구현; express your results this spring'):
            with self.subTest(text=text):
                row = course('good', [text], skills=[WEB])
                profile = resource_evidence.facts(row, self.project, self.selection)['suitability'][WEB]
                self.assertEqual(profile['missingStack'], [])
                self.assertEqual(profile['conflictingStack'], [])
                self.assertTrue(profile['suitable'])

    def test_core_technology_names_use_same_korean_boundaries_as_evidence(self):
        self.skill['coreCriteria'] = ['응답 코드 확인']
        for outcome, required in (('냉장고 재고 API 구현', []), ('장고만두 재고 API 구현', []),
                                   ('장고로만 REST API 구현', ['django'])):
            with self.subTest(outcome=outcome):
                self.skill['coreOutcome'] = outcome
                profile = resource_evidence.facts(self.django, self.project, self.selection)['suitability'][WEB]
                self.assertEqual(profile['requiredStack'], required)

    def test_core_runtime_conflict_uses_only_applied_technologies(self):
        self.skill.update(coreOutcome='Django REST API 구현', coreCriteria=['응답 코드 확인'])
        for text, runtime in (('Django 대신 Spring Boot로 REST API 구현 실습', 'java'),
                               ('Django 대신 Express.js로 REST API 구현 실습', 'javascript')):
            with self.subTest(text=text):
                row = course('wrong', [text], skills=[WEB], title='Django 비교 과정')
                profile = resource_evidence.facts(row, self.project, self.selection)['suitability'][WEB]
                self.assertEqual(profile['missingStack'], ['django'])
                self.assertEqual(profile['conflictingStack'], [runtime])
                self.assertFalse(profile['suitable'])

    def test_recommendation_rejects_excluded_technology_in_applied_evidence(self):
        self.project = {'goal': 'Django로 REST API 구현'}
        self.skill.update(coreOutcome='Django REST API 구현', coreCriteria=['응답 코드 확인'])
        self.django['hours'] = 5
        replacement = course('replacement', ['Django 대신 FastAPI로 REST API 구현'], skills=[WEB], hours=1)
        partial_name = course('partial-name', ['냉장고 재고 API 구현'], skills=[WEB], hours=1)
        items = {row['id']: row for row in (replacement, partial_name, self.django)}
        embed = Mock(return_value=[[1.0] + [0.0] * (resource_rag.DIMENSIONS - 1)])
        search = Mock(return_value=[{'resource_id': key, 'similarity': score}
                                    for key, score in [('replacement', .95), ('partial-name', .9), ('django', .8)]])
        pools, _ = resource_rag.retrieve(self.project, self.selection, items, self.option,
                                         embed=embed, search=search)
        self.assertEqual([row['id'] for row in pools[0]['courses']], ['django'])
        # 이전 추천 캐시에 제외된 강좌가 남은 경우에도 최종 선택을 검사한다.
        pools = [{'name': WEB, 'courses': list(items.values()), 'books': []}]
        generate = Mock(return_value={'skills': [{'name': WEB, 'books': [],
                                                   'courses': [{'id': 'django'}]}]})
        result = recommend_resources(self.project, self.selection, items, generate, course=self.option,
                                     retrieved_pools=pools)
        payload = generate.call_args.args[1]
        profiles = {row['title']: row['learningEvidence'] for row in payload['skills'][0]['courses']}
        for key in ('replacement', 'partial-name'):
            self.assertNotIn(key, profiles)
        self.assertEqual(payload['crashStudyPlan']['uniqueHours'], 5)
        self.assertEqual(result['skills'][0]['selectedCourse'], 'django')
        generate.return_value['skills'][0]['courses'] = [{'id': 'replacement'}, {'id': 'partial-name'}]
        with self.assertRaises(RecommendationError):
            recommend_resources(self.project, self.selection, items, generate, course=self.option,
                                retrieved_pools=pools)

    def test_core_keeps_english_framework_context_rules(self):
        self.skill['coreCriteria'] = ['응답 코드 확인']
        for outcome in ('FastAPI REST API 구현; express your results this spring',
                        'FastAPI REST API 구현 - spring semester'):
            with self.subTest(outcome=outcome):
                self.skill['coreOutcome'] = outcome
                profile = resource_evidence.facts(self.short, self.project, self.selection)['suitability'][WEB]
                self.assertEqual(profile['requiredStack'], ['fastapi'])
                self.assertTrue(profile['suitable'])
        name = 'RESTful API 설계'
        for outcome, stack in (('Spring API 구현', 'spring'), ('Spring Boot REST API 구현', 'spring'),
                               ('Spring AI REST API 구현', 'spring'), ('Express API 구현', 'express'),
                               ('Express.js REST API 구현', 'express')):
            with self.subTest(outcome=outcome):
                skill = dict(self.skill, name=name, coreOutcome=outcome)
                row = course('framework', [outcome + ' 실습'], skills=[name])
                profile = resource_evidence.facts(row, self.project, {'skills': [skill]})['suitability'][name]
                self.assertEqual(profile['requiredStack'], [stack])
                self.assertEqual(profile['missingStack'], [])
                self.assertTrue(profile['suitable'])

    def test_replacement_keeps_implementation_and_security_evidence_separate(self):
        self.skill.update(coreOutcome='FastAPI 대신 Django로 REST API 구현',
                          coreCriteria=['JWT 권한 경계 검증'])
        row = course('secure', ['Django REST API 구현 실습', 'JWT 권한 경계 검증 실습'], skills=[WEB])
        profile = resource_evidence.facts(row, self.project, self.selection)['suitability'][WEB]
        self.assertEqual(profile['requiredStage'], 'security')
        self.assertEqual(profile['requiredStack'], ['django'])
        self.assertEqual(profile['missingStack'], [])
        self.assertTrue(profile['suitable'])

        self.skill['coreCriteria'] = ['FastAPI 대신 Django에서 JWT 권한 경계 검증']
        profile = resource_evidence.facts(row, self.project, self.selection)['suitability'][WEB]
        self.assertEqual(profile['requiredStack'], ['django'])
        self.assertEqual(profile['missingStack'], ['django'])
        self.assertFalse(profile['suitable'])
        row['curriculum']['items'][1]['title'] = 'Django에서 JWT 권한 경계 검증 실습'
        profile = resource_evidence.facts(row, self.project, self.selection)['suitability'][WEB]
        self.assertTrue(profile['suitable'])

    def test_security_only_technology_requirement_needs_its_own_security_unit(self):
        self.skill['coreOutcome'] = 'REST API'
        for technology, stack in (('FastAPI', 'fastapi'), ('Django', 'django')):
            with self.subTest(technology=technology):
                self.skill['coreCriteria'] = [f'{technology}에서 JWT 권한 경계 검증']
                row = course('secure', [f'{technology} REST API 구현 실습', 'JWT 권한 경계 검증 실습'],
                             skills=[WEB])
                profile = resource_evidence.facts(row, self.project, self.selection)['suitability'][WEB]
                self.assertEqual(profile['requiredStack'], [stack])
                self.assertEqual(profile['missingStack'], [stack])
                self.assertEqual(profile['unitIndices'], [1])
                self.assertFalse(profile['suitable'])

                row['curriculum']['items'][1]['title'] = f'{technology}에서 JWT 권한 경계 검증 실습'
                profile = resource_evidence.facts(row, self.project, self.selection)['suitability'][WEB]
                self.assertEqual(profile['missingStack'], [])
                self.assertTrue(profile['suitable'])

    def test_security_replacement_does_not_require_excluded_stack_in_security_unit(self):
        self.skill.update(coreOutcome='FastAPI REST API 구현',
                          coreCriteria=['FastAPI 대신 Django에서 JWT 권한 경계 검증'])
        row = course('secure', ['FastAPI REST API 구현 실습', 'Django에서 JWT 권한 경계 검증 실습'],
                     skills=[WEB])
        profile = resource_evidence.facts(row, self.project, self.selection)['suitability'][WEB]
        self.assertEqual(profile['requiredStack'], ['django', 'fastapi'])
        self.assertEqual(profile['missingStack'], [])
        self.assertTrue(profile['suitable'])

        row['curriculum']['items'][1]['title'] = 'FastAPI에서 JWT 권한 경계 검증 실습'
        profile = resource_evidence.facts(row, self.project, self.selection)['suitability'][WEB]
        self.assertEqual(profile['missingStack'], ['django'])
        self.assertFalse(profile['suitable'])

    def test_security_evidence_does_not_teach_excluded_or_partial_technology_names(self):
        self.skill.update(coreOutcome='Django REST API 구현', coreCriteria=['Django에서 JWT 권한 경계 검증'])
        for security in ('Django 대신 FastAPI에서 JWT 권한 경계 검증 실습',
                         'FastAPI에서 JWT 권한 경계 검증 실습 후 Django 비교',
                         '냉장고 재고 API 구현 및 권한 경계 검증 실습'):
            with self.subTest(security=security):
                row = course('wrong', ['Django REST API 구현 실습', security], skills=[WEB])
                profile = resource_evidence.facts(row, self.project, self.selection)['suitability'][WEB]
                self.assertEqual(profile['requiredStack'], ['django'])
                self.assertEqual(profile['missingStack'], ['django'])
                self.assertFalse(profile['suitable'])
        row = course('good', ['Django REST API 구현 실습', '장고에서 JWT 권한 경계 검증 실습'], skills=[WEB])
        self.assertTrue(resource_evidence.suitable(resource_evidence.facts(row, self.project, self.selection), WEB))

    def test_separate_build_evidence_does_not_teach_excluded_or_partial_technology_names(self):
        self.skill.update(coreOutcome='Django REST API 구현', coreCriteria=['JWT 권한 경계 검증'])
        for build in ('Django 대신 FastAPI로 REST API 구현 실습', '냉장고 재고 API 구현 실습'):
            with self.subTest(build=build):
                row = course('wrong', [build, 'JWT 권한 경계 검증 실습'], skills=[WEB])
                profile = resource_evidence.facts(row, self.project, self.selection)['suitability'][WEB]
                self.assertEqual(profile['missingStack'], ['django'])
                self.assertFalse(profile['suitable'])
        row = course('good', ['장고로만 REST API 구현 실습', 'JWT 권한 경계 검증 실습'], skills=[WEB])
        self.assertTrue(resource_evidence.suitable(resource_evidence.facts(row, self.project, self.selection), WEB))

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

    def test_skill_without_core_keeps_full_scope(self):
        skill = {'name': WEB, 'application': 'FastAPI와 Django REST API 구현'}
        profiles = resource_evidence.facts(self.short, self.project, {'skills': [skill]})['suitability']
        self.assertEqual(profiles[WEB]['missingStack'], ['django'])
