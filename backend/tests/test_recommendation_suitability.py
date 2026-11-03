"""단계·구현 기술의 과대 인정 회귀. 실제 카탈로그는 외부 읽기 전용 스냅샷으로만 검사한다."""
from copy import deepcopy
import json
import os
from pathlib import Path
import unicodedata
import unittest
from unittest.mock import Mock

from app.agents.resource_recommendations import RecommendationError, recommend_resources
from app.services import crash_courses as crash, resource_evidence as evidence

RAG = 'RAG & 생성형 AI 에이전트'
WEB = '웹 프레임워크 (FastAPI/Django)'
SERVING = 'MLOps & 모델 서빙'
NLP = '자연어 처리(NLP) & LLM 기초'


def course(key, titles, *, skills=None, hours=2, content='', title=None):
    return {'id': key, 'title': title or key, 'type': 'course', 'usable': True,
            'skills': skills or [RAG], 'cost': 0, 'hours': hours, 'estimated': [],
            'timeStatus': 'confirmed', 'content': content,
            'curriculum': {'items': [{'title': value} for value in titles]}, 'retrievalScore': .8}


class SuitabilityTests(unittest.TestCase):
    def setUp(self):
        self.project = {'goal': '사내 규정 문서로 RAG 챗봇을 만들고 FastAPI로 배포'}
        self.selection = {'skills': [{'name': RAG, 'application': '문서 RAG 챗봇 구현'},
                                     {'name': WEB, 'application': 'FastAPI 서버 구현'},
                                     {'name': SERVING, 'application': '모델 서빙과 배포'}]}

    def facts(self, row):
        return evidence.facts(row, self.project, self.selection)

    def test_intro_and_design_do_not_equal_implementation_before_duration_comparison(self):
        intro = course('intro', ['RAG 동작 원리와 구조', '권한 경계 지도 작성'], hours=.3)
        design = course('design', ['검색 보강(RAG) 설계', '서비스 UX 디자인 실습'], hours=.5)
        actual = course('actual', ['RAG 검색과 문서 챗봇 구현'], hours=8)
        ranked = crash.rank([intro, design, actual], self.project, self.selection, self.selection['skills'][0])
        self.assertEqual(ranked[0]['id'], 'actual')
        self.assertEqual(len(ranked), 3)
        self.assertFalse(evidence.suitable(self.facts(intro), RAG))
        self.assertFalse(evidence.suitable(self.facts(design), RAG))

    def test_implementation_overview_is_conceptual_and_incidental_mentions_stay_mentions(self):
        intro = course('intro', ['RAG 구현 개요'])
        self.assertFalse(evidence.suitable(self.facts(intro), RAG))
        self.assertEqual(self.facts(intro)['suitability'][RAG]['evidenceLevel'], 'conceptual')
        mention = course('mention', ['RAG의 미래와 시장 동향'])
        self.assertEqual(self.facts(mention)['suitability'][RAG]['evidenceLevel'], 'mention')

    def test_applied_learning_unit_is_visible_even_when_other_units_repeat_goal_words(self):
        row = course('actual', ['문서 RAG 챗봇 소개', '문서 RAG 챗봇 개요', '문서 RAG 챗봇 구조',
                                '벡터 재순위화 구현'], content='RAG 검색 증강')
        units = evidence.outline(row, self.project, self.selection, self.selection['skills'][0])
        self.assertIn(3, [unit['index'] for unit in units])

    def test_discussion_questions_and_development_tips_do_not_prove_implementation(self):
        row = course('discussion', ['Q. RAG 구현 프로세스가 궁금해요.', 'Q. 사내 챗봇을 만드는 방법이 궁금해요.'],
                     content='RAG를 활용한 LLM 애플리케이션 개발 팁', hours=.5)
        for unit in row['curriculum']['items']:
            unit['section'] = 'Q&A 세션'
        profile = self.facts(row)['suitability'][RAG]
        self.assertEqual(profile['evidenceLevel'], 'conceptual')
        self.assertEqual(profile['unitIndices'], [])
        self.assertFalse(profile['suitable'])
        actual = course('actual', ['RAG 문서 검색 구현 실습'], hours=4)
        ranked = crash.rank([row, actual], self.project, self.selection, self.selection['skills'][0])
        self.assertEqual(ranked[0]['id'], 'actual')
        selection = {'skills': [self.selection['skills'][0]]}
        self.assertIsNone(crash.study_plan([{'name': RAG, 'courses': [row], 'books': []}],
                                         self.project, selection, {'discussion': 'S1-C1'}, cache={}))

    def test_discussion_material_keeps_conceptual_value_and_real_labs(self):
        row = course('mixed', ['RAG 동작 원리 소개', 'Q. RAG 챗봇을 만드는 방법이 궁금해요.'],
                     title='RAG 경험 공유와 개발 팁', content='RAG 애플리케이션 개발 팁')
        selection = {'skills': [{'name': RAG, 'application': 'RAG 동작 원리 이해'}]}
        self.assertTrue(evidence.suitable(evidence.facts(row, self.project, selection), RAG))
        row['curriculum']['items'].append({'title': '실습: RAG 문서 검색 챗봇 구현'})
        profile = self.facts(row)['suitability'][RAG]
        self.assertTrue(profile['suitable'])
        self.assertIn(2, profile['unitIndices'])

    def test_question_style_tutorial_is_valid_when_it_is_an_actual_lab(self):
        row = course('lab', ['실습: RAG 검색 챗봇을 어떻게 구현하나요?'])
        self.assertTrue(evidence.suitable(self.facts(row), RAG))

    def test_one_matching_anchor_cannot_hide_a_conflicting_implementation_stack(self):
        spring = course('spring', ['Spring AI RAG 검색 구현', 'RAG REST API 구현'],
                        skills=[RAG, WEB], title='Spring RAG', hours=.2)
        actual = course('actual', ['RAG 문서 검색 구현', 'FastAPI 서버 실행'], skills=[RAG, WEB], hours=8)
        for skill in self.selection['skills'][:2]:
            self.assertFalse(evidence.suitable(self.facts(spring), skill['name']))
            self.assertTrue(evidence.suitable(self.facts(actual), skill['name']))
            self.assertEqual(crash.rank([spring, actual], self.project, self.selection, skill)[0]['id'], 'actual')

    def test_framework_comparison_mention_does_not_prove_its_implementation(self):
        row = course('comparison', ['FastAPI와 Spring 비교', 'Spring REST API 구현'], skills=[WEB])
        info = self.facts(row)['suitability'][WEB]
        self.assertIn('fastapi', info['missingStack'])
        self.assertFalse(info['suitable'])

    def test_service_design_and_model_business_plans_do_not_teach_model_deployment(self):
        row = course('design', ['비즈니스 모델 설계', 'LLM 서비스 기획 실습'], skills=[SERVING])
        row['curriculum']['items'][0]['section'] = '운영·모니터링·MLOps(운영적 관점)'
        row['content'] = '운영·모니터링·MLOps(운영적 관점)\n비즈니스 모델 설계\nLLM 서비스 기획 실습'
        self.assertFalse(evidence.suitable(self.facts(row), SERVING))
        actual = course('serving', ['모델 서빙 API 구현과 배포', 'MLOps 모니터링 실습'], skills=[SERVING])
        self.assertTrue(evidence.suitable(self.facts(actual), SERVING))

    def test_related_security_learning_and_concepts_remain_valid_goals(self):
        row = course('security', ['RAG 동작 원리', '공격 표면 지도 작성', '권한 경계 시험과 진단'])
        for application in ('RAG 동작 원리 이해', 'RAG 공격 표면 지도 작성과 권한 경계 검증'):
            selection = {'skills': [{'name': RAG, 'application': application}]}
            info = evidence.facts(row, {'goal': application}, selection)
            self.assertTrue(evidence.suitable(info, RAG))

    def test_language_independent_learning_does_not_require_web_implementation_stack(self):
        row = course('sql', ['SQL 조인 원리', 'SQL 정규화 이론'], skills=['SQL'])
        selection = {'skills': [{'name': 'SQL', 'application': 'SQL 조인 원리 이해'}]}
        info = evidence.facts(row, self.project, selection)
        self.assertTrue(evidence.suitable(info, 'SQL'))
        self.assertEqual(info['suitability']['SQL']['requiredStack'], [])

    def test_nfd_korean_is_normalized_in_evidence_and_excerpts_without_source_mutation(self):
        title = unicodedata.normalize('NFD', 'RAG 문서 검색 챗봇 구현')
        row = course('nfd', [title])
        original = deepcopy(row)
        self.assertTrue(evidence.suitable(self.facts(row), RAG))
        units = evidence.outline(row, self.project, self.selection, self.selection['skills'][0])
        self.assertEqual(units[0]['title'], unicodedata.normalize('NFKC', title))
        self.assertEqual(row, original)

    def test_suspended_curriculum_cannot_reenter_from_description(self):
        row = course('suspended', ['RAG 문서 챗봇 구현'])
        row['curriculum']['items'][0]['suspended'] = True
        row['content'] = 'RAG 문서 챗봇 구현'
        self.assertFalse(evidence.suitable(self.facts(row), RAG))

    def test_joint_plan_checks_all_skill_suitability_not_topic_support(self):
        shared = course('shared', ['RAG 문서 검색 구현', 'FastAPI 개요'], skills=[RAG, WEB])
        info = self.facts(shared)
        self.assertEqual(info['supported'], [RAG, WEB])
        pools = [{'name': skill['name'], 'courses': [shared], 'books': []} for skill in self.selection['skills'][:2]]
        selection = {'skills': self.selection['skills'][:2]}
        self.assertIsNone(crash.study_plan(pools, self.project, selection, {'shared': 'S1-C1'}, cache={}))
        shared['curriculum']['items'].append({'title': 'FastAPI 서버 실행'})
        plan = crash.study_plan(pools, self.project, selection, {'shared': 'S1-C1'}, cache={})
        self.assertEqual(plan['uniqueCourses'], 1)
        self.assertEqual(plan['uniqueHours'], 2)

    def test_suitable_candidate_outside_intro_similarity_window_is_still_reviewed(self):
        intro = course('intro', ['RAG 개요'], hours=.1)
        actual = course('actual', ['RAG 문서 검색 구현'], hours=10)
        intro['retrievalScore'], actual['retrievalScore'] = .95, .7
        result = crash.rank([intro, actual], self.project, self.selection, self.selection['skills'][0])
        self.assertEqual([row['id'] for row in result], ['actual', 'intro'])

    def test_diagnostics_are_optional_bounded_and_do_not_retry_or_force_choices(self):
        row = course('intro', ['RAG 개요'])
        selection = {'skills': [self.selection['skills'][0]]}
        pools = [{'name': RAG, 'courses': [row], 'books': []}]
        raw = {'skills': [{'name': RAG, 'courses': [], 'books': [],
                           'courseDiagnostic': {'reason': 'insufficient_evidence', 'detail': '구현 단원 근거가 부족합니다.'}}]}
        model = Mock(return_value=raw)
        result = recommend_resources(self.project, selection, {'intro': row}, model, course={'id': 'A2'}, retrieved_pools=pools)
        model.assert_called_once()
        self.assertIsNone(result['skills'][0]['selectedCourse'])
        self.assertEqual(result['skills'][0]['courseDiagnostic'], raw['skills'][0]['courseDiagnostic'])
        payload = model.call_args.args[1]
        self.assertIsNone(payload['crashStudyPlan'])
        self.assertEqual(payload['skills'][0]['courses'][0]['learningEvidence']['evidenceLevel'], 'conceptual')
        for diagnostic in ({'reason': 'invented', 'detail': '사유'}, {'reason': 'scope_gap', 'detail': 'x' * 241},
                           {'reason': 'scope_gap', 'detail': ' '}, {'reason': 'scope_gap', 'detail': '사유', 'extra': True},
                           {'reason': 'longer_for_coverage', 'detail': '사유'}, {'reason': 'no_candidates', 'detail': '사유'}):
            with self.subTest(diagnostic=diagnostic), self.assertRaises(RecommendationError):
                bad = deepcopy(raw)
                bad['skills'][0]['courseDiagnostic'] = diagnostic
                recommend_resources(self.project, selection, {'intro': row}, lambda *_: bad,
                                    course={'id': 'A2'}, retrieved_pools=pools)

    def test_longer_choice_diagnostic_preserves_model_choice_and_legacy_key_responses(self):
        rows = [course('short', ['RAG 문서 검색 구현'], hours=1), course('long', ['RAG 문서 검색 구현과 평가'], hours=9)]
        pools = [{'name': RAG, 'courses': rows, 'books': []}]
        selection = {'skills': [self.selection['skills'][0]]}
        def generate(_, payload):
            chosen = next(row for row in payload['skills'][0]['courses'] if row['title'] == 'long')
            return {'skills': [{'name': RAG, 'courses': [{'key': chosen['choiceKey']}], 'books': [],
                                'courseDiagnostic': {'reason': 'longer_for_coverage', 'detail': '검색 품질 평가도 필요합니다.'}}]}
        result = recommend_resources(self.project, selection, {row['id']: row for row in rows}, generate,
                                     course={'id': 'A2'}, retrieved_pools=pools)
        self.assertEqual(result['skills'][0]['selectedCourse'], 'long')
        self.assertEqual(len(result['skills'][0]['courses']), 1)

    def test_partial_coverage_diagnostic_can_accompany_a_valid_course_choice(self):
        row = course('actual', ['RAG 문서 검색 구현'])
        selection = {'skills': [self.selection['skills'][0]]}
        pools = [{'name': RAG, 'courses': [row], 'books': []}]
        for reason in ('scope_gap', 'insufficient_evidence', 'stack_mismatch'):
            with self.subTest(reason=reason):
                diagnostic = {'reason': reason, 'detail': '문서 검색 구현은 있지만 권한 경계 검증 근거는 부족합니다.'}
                raw = {'skills': [{'name': RAG, 'courses': [{'key': 'S1-C1'}], 'books': [],
                                   'courseDiagnostic': diagnostic}]}
                model = Mock(return_value=raw)
                result = recommend_resources(self.project, selection, {'actual': row}, model,
                                             course={'id': 'A2'}, retrieved_pools=pools)
                model.assert_called_once()
                skill = result['skills'][0]
                self.assertEqual(skill['selectedCourse'], 'actual')
                self.assertEqual(skill['courseDiagnostic'], diagnostic)
                self.assertEqual([card['id'] for card in skill['courses']], ['actual'])

    def test_partial_diagnostic_does_not_relax_resource_choice_validation(self):
        row = course('actual', ['RAG 문서 검색 구현'])
        selection = {'skills': [self.selection['skills'][0]]}
        pools = [{'name': RAG, 'courses': [row], 'books': []}]
        for courses in ([{'key': 'invented'}], [{'key': 'S1-C1'}, {'key': 'S1-C1'}]):
            with self.subTest(courses=courses), self.assertRaises(RecommendationError):
                raw = {'skills': [{'name': RAG, 'courses': courses, 'books': [],
                                   'courseDiagnostic': {'reason': 'scope_gap', 'detail': '일부 내용이 부족합니다.'}}]}
                recommend_resources(self.project, selection, {'actual': row}, lambda *_: raw,
                                    course={'id': 'A2'}, retrieved_pools=pools)

    def test_explicit_coverage_reason_keeps_longer_first_choice_when_shorter_alternative_is_returned(self):
        short = course('short', ['RAG 문서 검색 구현'], skills=[RAG, WEB], hours=1)
        long = course('long', ['RAG 문서 검색 구현과 평가', 'FastAPI 서버 실행'], skills=[RAG, WEB], hours=9)
        selection = {'skills': self.selection['skills'][:2]}
        pools = [{'name': skill['name'], 'courses': [short, long], 'books': []} for skill in selection['skills']]
        def generate(_, payload):
            keys = {row['title']: row['choiceKey'] for row in payload['skills'][0]['courses']}
            return {'skills': [{'name': skill['name'], 'courses': [{'key': keys['long']}, {'key': keys['short']}],
                                'books': [], 'courseDiagnostic': {'reason': 'longer_for_coverage',
                                'detail': '검색 품질 평가와 FastAPI 실행을 함께 학습해야 합니다.'}}
                               for skill in selection['skills']]}
        result = recommend_resources(self.project, selection, {'short': short, 'long': long}, generate,
                                     course={'id': 'A2'}, retrieved_pools=pools)
        self.assertEqual([skill['selectedCourse'] for skill in result['skills']], ['long', 'long'])
        self.assertTrue(all(skill['courses'][0]['aiRecommended'] for skill in result['skills']))


@unittest.skipUnless(os.environ.get('RECOMMENDATION_CATALOG_SNAPSHOT'), '외부 실제 카탈로그 스냅샷 미지정')
class SnapshotSuitabilityTests(unittest.TestCase):
    """원문을 저장소에 복사하지 않고 실제 강좌의 음성·양성 사례를 대조한다."""
    setUp = SuitabilityTests.setUp
    facts = SuitabilityTests.facts

    @classmethod
    def setUpClass(cls):
        snapshot = json.loads(Path(os.environ['RECOMMENDATION_CATALOG_SNAPSHOT']).read_text(encoding='utf-8'))
        cls.records = snapshot['records']

    def test_actual_review_negatives_and_actual_positive_implementations(self):
        for key, skill in (('INFLEARN_344565', RAG), ('INFLEARN_337694', SERVING), ('INFLEARN_342600', RAG),
                           ('INFLEARN_334856', RAG)):
            with self.subTest(key=key, skill=skill):
                self.assertFalse(evidence.suitable(self.facts(self.records[key]), skill))
        for key, skill in (('INFLEARN_342279', RAG), ('INFLEARN_342279', WEB), ('INFLEARN_331295', WEB),
                           ('INFLEARN_333796', RAG), ('MS_c4c5fa9a9528', RAG)):
            with self.subTest(key=key, skill=skill):
                self.assertTrue(evidence.suitable(self.facts(self.records[key]), skill))

    def test_actual_intro_security_and_spring_concepts_are_preserved(self):
        for key, application in (('INFLEARN_344565', 'RAG 동작 원리 이해'),
                                 ('INFLEARN_344565', 'RAG 공격 표면 지도 작성과 권한 경계 검증'),
                                 ('INFLEARN_344569', 'RAG 검색 권한 경계 검증'),
                                 ('INFLEARN_342600', 'RAG 구조와 검색 증강 원리 이해')):
            with self.subTest(key=key, application=application):
                info = evidence.facts(self.records[key], {'goal': application},
                                      {'skills': [{'name': RAG, 'application': application}]})
                self.assertTrue(evidence.suitable(info, RAG))

    def test_actual_catalog_retains_candidates_for_each_target_class(self):
        for skill in self.selection['skills']:
            rows = [dict(row, retrievalScore=.8) for row in self.records.values()
                    if row['type'] == 'course' and row['usable'] and skill['name'] in row['skills']]
            cache = {row['id']: self.facts(row) for row in rows}
            self.assertTrue(any(evidence.suitable(info, skill['name']) for info in cache.values()), skill['name'])
            ranked = crash.rank(rows, self.project, self.selection, skill, limit=6, cache=cache)
            self.assertEqual(len(ranked), min(6, len(rows)))
            self.assertTrue(evidence.suitable(cache[ranked[0]['id']], skill['name']))


if __name__ == '__main__':
    unittest.main()
