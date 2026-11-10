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
        row = course('lab', ['실습: RAG 문서 검색 챗봇을 어떻게 구현하나요?'])
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

    def test_english_learning_units_are_not_business_ui_substrings(self):
        selection = {'skills': [{'name': NLP, 'application': 'LLM 챗봇 구현'}]}
        for text in ('Building a RAG chatbot with LangChain', 'LLM 앱 빌드 guide',
                     'Linux 환경에서 LLM 모델 실행', 'LLM chatbot 구현 guide'):
            with self.subTest(text=text):
                row = course('nlp', [text], skills=[NLP], title='LLM 실습')
                self.assertFalse(evidence._business.search(text))
                profile = evidence.facts(row, {'goal': 'LLM 챗봇 구현'}, selection)['suitability'][NLP]
                self.assertTrue(profile['suitable'])
                self.assertEqual(profile['unitIndices'], [0])
                # 같은 본문이 소개에서 확보된 경우에도 학습 근거를 유지한다.
                row['curriculum']['items'] = []
                row['content'] = text
                self.assertTrue(evidence.suitable(evidence.facts(row, {'goal': 'LLM 챗봇 구현'}, selection), NLP))

    def test_business_ui_is_not_nlp_merely_because_it_mentions_llm(self):
        selection = {'skills': [{'name': NLP, 'application': 'LLM 챗봇 구현'}]}
        for text in ('LLM 서비스 UI 디자인 실습', 'chatbot UX디자인 실습', 'LLM business 기획 실습'):
            with self.subTest(text=text):
                row = course('business', [text], skills=[NLP])
                self.assertTrue(evidence._business.search(text))
                self.assertFalse(evidence.suitable(evidence.facts(row, {'goal': 'LLM 챗봇 구현'}, selection), NLP))

    def test_english_verbs_and_seasons_are_not_framework_conflicts(self):
        selection = {'skills': [{'name': RAG, 'application': 'RAG chatbot 구현'}]}
        for text in ('Build a RAG chatbot and express your results',
                     'Build a RAG chatbot - spring semester', 'Build a RAG chatbot this spring'):
            with self.subTest(text=text):
                row = course('neutral', [text])
                info = evidence.facts(row, {'goal': 'Python RAG chatbot 구현'}, selection)['suitability'][RAG]
                self.assertTrue(info['suitable'])
                self.assertEqual(info['conflictingStack'], [])
        # 목표의 일반 영어 단어도 별도 프레임워크를 요구하는 조건으로 바꾸지 않는다.
        row = course('python', ['FastAPI 서버 구현'], skills=[WEB])
        selection = {'skills': [{'name': WEB, 'application': 'FastAPI 서버 구현'}]}
        profile = evidence.facts(row, {'goal': 'FastAPI 서버 구현; express your results this spring'}, selection)['suitability'][WEB]
        self.assertEqual(profile['requiredStack'], ['fastapi'])
        self.assertTrue(profile['suitable'])

    def test_explicit_spring_and_express_frameworks_still_conflict_with_python(self):
        selection = {'skills': [{'name': RAG, 'application': 'RAG chatbot 구현'}]}
        for text, runtime in (('Spring Boot RAG 구현', 'java'), ('Spring AI RAG 구현', 'java'),
                              ('Spring REST API RAG 구현', 'java'), ('Java / Spring RAG 구현', 'java'),
                              ('Express.js RAG 구현', 'javascript'), ('Express로 RAG API 구현', 'javascript'),
                              ('Node.js / Express RAG 구현', 'javascript')):
            with self.subTest(text=text):
                row = course('framework', [text])
                profile = evidence.facts(row, {'goal': 'Python RAG chatbot 구현'}, selection)['suitability'][RAG]
                self.assertFalse(profile['suitable'])
                self.assertEqual(profile['conflictingStack'], [runtime])
        for text, name in (('Spring API 구현', 'spring'), ('Express API 구현', 'express')):
            web_name = 'RESTful API 설계'
            row = course('web', [text], skills=[web_name])
            context = {'skills': [{'name': web_name, 'application': text}]}
            profile = evidence.facts(row, {'goal': text}, context)['suitability'][web_name]
            self.assertEqual(profile['requiredStack'], [name])
            self.assertEqual(profile['missingStack'], [])
            self.assertTrue(profile['suitable'])

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
        # 형식 검사는 코스 정책과 분리한다. 엄격한 코스 입력은 근거 없는 후보를 모델 호출 전에 제거한다.
        row = course('intro', ['RAG 개요'])
        selection = {'skills': [self.selection['skills'][0]]}
        pools = [{'name': RAG, 'courses': [row], 'books': []}]
        raw = {'skills': [{'name': RAG, 'courses': [], 'books': [],
                           'courseDiagnostic': {'reason': 'insufficient_evidence', 'detail': '구현 단원 근거가 부족합니다.'}}]}
        model = Mock(return_value=raw)
        result = recommend_resources(self.project, selection, {'intro': row}, model, retrieved_pools=pools)
        model.assert_called_once()
        self.assertIsNone(result['skills'][0]['selectedCourse'])
        self.assertEqual(result['skills'][0]['courseDiagnostic'], raw['skills'][0]['courseDiagnostic'])
        payload = model.call_args.args[1]
        self.assertNotIn('crashStudyPlan', payload)
        self.assertEqual(payload['skills'][0]['courses'][0]['learningEvidence']['evidenceLevel'], 'conceptual')
        # 진단 형식·사유 오류는 추천 전체를 실패시키지 않고 서버가 계산한 안내로 대체한다.
        fallback = recommend_resources(self.project, selection, {'intro': row}, lambda *_: dict(raw, skills=[
            dict(raw['skills'][0], courseDiagnostic=None)]), retrieved_pools=pools)
        server = fallback['skills'][0]['courseDiagnostic']
        for diagnostic in ({'reason': 'invented', 'detail': '사유'}, {'reason': 'scope_gap', 'detail': ' '},
                           {'reason': 'longer_for_coverage', 'detail': '사유'}, {'reason': 'no_candidates', 'detail': '사유'},
                           'scope_gap'):
            with self.subTest(diagnostic=diagnostic), self.assertLogs('app.agents.resource_recommendations', 'WARNING'):
                bad = deepcopy(raw)
                bad['skills'][0]['courseDiagnostic'] = diagnostic
                result = recommend_resources(self.project, selection, {'intro': row}, lambda *_: bad,
                                             retrieved_pools=pools)
                self.assertEqual(result['skills'][0]['courseDiagnostic'], server)
        long = deepcopy(raw)
        long['skills'][0]['courseDiagnostic'] = {'reason': 'scope_gap', 'detail': 'x' * 300, 'extra': True}
        kept = recommend_resources(self.project, selection, {'intro': row}, lambda *_: long,
                                   retrieved_pools=pools)['skills'][0]['courseDiagnostic']
        self.assertEqual(kept, {'reason': 'scope_gap', 'detail': 'x' * 239 + '…'})

    def test_longer_choice_diagnostic_preserves_model_choice_and_legacy_key_responses(self):
        rows = [course('short', ['RAG 문서 검색 구현'], hours=1),
                course('long', ['RAG 문서 검색 구현', 'RAG 검색 품질 평가'], hours=9)]
        pools = [{'name': RAG, 'courses': rows, 'books': []}]
        selection = {'skills': [dict(self.selection['skills'][0], completionCriteria=['검색 품질 평가'])]}
        def generate(_, payload):
            chosen = next(row for row in payload['skills'][0]['courses'] if row['title'] == 'long')
            return {'skills': [{'name': RAG, 'courses': [{'key': chosen['choiceKey']}], 'books': [],
                                'courseDiagnostic': {'reason': 'longer_for_coverage', 'detail': '검색 품질 평가도 필요합니다.'}}]}
        result = recommend_resources(self.project, selection, {row['id']: row for row in rows}, generate,
                                     course={'id': 'A2'}, retrieved_pools=pools)
        self.assertEqual(result['skills'][0]['selectedCourse'], 'long')
        self.assertEqual(result['skills'][0]['courseDiagnostic']['reason'], 'longer_for_coverage')
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

    def test_shared_longer_course_wins_when_it_alone_covers_every_returned_skill(self):
        short = course('short', ['RAG 문서 검색 구현'], skills=[RAG, WEB], hours=1)
        long = course('long', ['RAG 문서 검색 구현과 평가', 'FastAPI 엔드포인트 구현과 서버 실행'], skills=[RAG, WEB], hours=9)
        selection = {'skills': self.selection['skills'][:2]}
        pools = [{'name': skill['name'], 'courses': [short, long], 'books': []} for skill in selection['skills']]
        def generate(_, payload):
            return {'skills': [{'name': skill['name'], 'courses': [{'key': card['choiceKey']}
                                for card in sorted(pool['courses'], key=lambda row: row['title'])],
                                'books': [], 'courseDiagnostic': {'reason': 'longer_for_coverage',
                                'detail': '검색 품질 평가와 FastAPI 실행을 함께 학습해야 합니다.'}}
                               for skill, pool in zip(selection['skills'], payload['skills'])]}
        result = recommend_resources(self.project, selection, {'short': short, 'long': long}, generate,
                                     course={'id': 'A2'}, retrieved_pools=pools)
        self.assertEqual([skill['selectedCourse'] for skill in result['skills']], ['long', 'long'])
        self.assertTrue(all(skill['courses'][0]['aiRecommended'] for skill in result['skills']))

    def test_missing_course_reason_falls_back_to_confirmed_stack_or_scope_gap(self):
        cases = (
            (self.selection['skills'][1], ['Spring REST API 구현'], 'stack_mismatch'),
            (self.selection['skills'][0], ['RAG 이미지 검색 앱 구현'], 'scope_gap'),
        )
        for skill, units, reason in cases:
            with self.subTest(reason=reason):
                name = skill['name']
                row = course('mismatch', units, skills=[name])
                row['difficulty'] = 'ADVANCED'
                pools = [{'name': name, 'courses': [row], 'books': []}]
                raw = {'skills': [{'name': name, 'courses': [], 'books': []}]}
                result = recommend_resources(self.project, {'skills': [skill]}, {'mismatch': row}, lambda *_: raw,
                                             course={'id': 'A3'}, retrieved_pools=pools)
                self.assertEqual(result['skills'][0]['courseDiagnostic']['reason'], reason)

    def test_transferable_rag_retrieval_is_useful_without_claiming_document_ingestion(self):
        general = course('general', ['RAG 실습: 벡터 DB 구성과 벡터 데이터 저장', 'RAG 조회와 챗봇 구현'])
        image_only = course('image', ['이미지 검색용 벡터 DB 구성', '이미지 검색 RAG 앱 구현'], title='이미지 검색 전용 RAG')
        general_info = self.facts(general)
        self.assertTrue(evidence.suitable(general_info, RAG))
        self.assertEqual(general_info['suitability'][RAG]['unverifiedTargetTopics'], ['문서 입력·전처리'])
        self.assertFalse(evidence.suitable(self.facts(image_only), RAG))


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
