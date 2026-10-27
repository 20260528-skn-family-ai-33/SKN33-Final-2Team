from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import unittest
from unittest.mock import MagicMock, patch

from src.shared.catalog_eligibility import exclusion_reason
from src.shared.catalog_scope import scope_reason, scoped_matches
from src.shared.skill_matching import SkillMatcher
from src.database.ingestion.course_supplement import validate_rows, insert_approved

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)
SKILLS = [{'skill_id': 1, 'name': 'SQL 기본 문법 & 조인', 'category': '데이터베이스'},
          {'skill_id': 2, 'name': 'SQL 쿼리 튜닝 & 인덱스 최적화', 'category': '데이터베이스'},
          {'skill_id': 16, 'name': 'TCP/IP 네트워크 프로토콜', 'category': '네트워크'}]


def course():
    url = 'https://www.kocw.net/home/search/kemView.do?kemId=1234567'
    return {'source': 'WEB_KOCW', 'external_key': '1234567', 'fetched_at': NOW,
            'reviewed_skill_ids': [1],
            'fields': dict(course_id='KOCW_1234567', title='SQL 실무', org_name='대학교',
                           platform='KOCW', url=url, source_url=url, record_source='WEB_KOCW',
                           source_verified_at=NOW, content_status='ready',
                           syllabus_summary='MySQL과 SQL을 사용하여 테이블을 설계하고 SELECT, JOIN 및 서브쿼리 문법을 직접 작성하는 실습 과정입니다.'),
            'raw': {'source_id': '1234567', 'url': url, 'http_status': 200,
                    'available_until': '2026-12-31T00:00:00+09:00',
                    'lessons': [{'title': t, 'video_listed': True, 'player_action_present': True,
                                 'suspended_marker': False} for t in ('SQL 기초', 'JOIN 실습')]}}


class CourseSupplementTests(unittest.TestCase):
    def reason(self, row):
        return exclusion_reason('courses', row['fields'], row['source'], row['raw'], row['fetched_at'], now=NOW)

    def test_public_kocw_curriculum_and_fresh_evidence_accepted(self):
        row = course()
        self.assertIsNone(self.reason(row))
        self.assertEqual(set(validate_rows([row], SKILLS, [], now=NOW)[0]['matches']), {1})

    def test_kocw_stale_or_expired_evidence_rejected(self):
        row = course(); row['fetched_at'] = '2026-09-01T00:00:00+00:00'
        self.assertEqual(self.reason(row), 'missing_or_expired_availability_evidence')
        row = course(); row['raw']['available_until'] = '2026-10-25T00:00:00+09:00'
        self.assertEqual(self.reason(row), 'missing_current_kocw_public_curriculum')

    def test_kocw_documents_or_suspended_video_are_not_public_video_proof(self):
        for field, value in (('video_listed', False), ('player_action_present', False), ('suspended_marker', True)):
            row = course(); row['raw']['lessons'][0][field] = value
            self.assertEqual(self.reason(row), 'missing_current_kocw_public_curriculum')
        row = course(); row['raw']['lessons'] = None
        self.assertEqual(self.reason(row), 'missing_current_kocw_public_curriculum')

    def test_source_host_id_and_detail_path_cannot_be_spoofed(self):
        for url in ('https://example.com/home/search/kemView.do?kemId=1234567',
                    'https://www.kocw.net/other?kemId=1234567',
                    'https://www.kocw.net/home/search/kemView.do?kemId=9999999'):
            row = course(); row['fields']['url'] = row['raw']['url'] = url
            self.assertEqual(self.reason(row), 'missing_current_kocw_public_curriculum')

    def test_sql_module_generic_title_needs_official_sql_product_and_curriculum(self):
        fields = dict(title='성능 향상 평가', url='https://learn.microsoft.com/ko-kr/training/modules/evaluate-performance-improvements/',
                      syllabus_summary='SQL Server의 인덱스를 조정하고 쿼리 힌트를 활용하며 실행 계획과 대기 통계를 분석하여 성능을 개선하는 방법을 학습합니다.')
        self.assertIsNone(scope_reason('courses', fields, 'API_MS_LEARN', {'type': 'module', 'products': ['sql-server']}))
        self.assertEqual(scope_reason('courses', fields, 'API_MS_LEARN', {'type': 'module', 'products': ['m365']}), 'scope_title_not_it_specialty')
        self.assertEqual(scope_reason('books', fields, 'API_DATA4LIBRARY', {'class_no': '005'}), 'scope_title_not_it_specialty')

    def test_tuning_requires_relational_sql_context_and_technical_network_topics_match(self):
        matcher = SkillMatcher(SKILLS)
        self.assertIn(2, scoped_matches(matcher, {'description': 'SQL Server 실행 계획을 비교하고 인덱스 조정을 실습합니다.'}))
        self.assertNotIn(2, scoped_matches(matcher, {'description': '프로젝트 실행 계획과 책의 인덱스 형식을 비교합니다.'}))
        self.assertNotIn(2, scoped_matches(matcher, {'description': 'Azure Cosmos DB NoSQL 인덱스 최적화를 실습합니다.'}))
        self.assertIn(16, scoped_matches(matcher, {'description': 'IP 주소 및 서브넷을 구성하고 TCP 패킷을 분석합니다.'}))
        self.assertNotIn(16, scoped_matches(matcher, {'description': 'Blazor 페이지 라우팅과 메뉴 경로를 디자인합니다.'}))

    def test_duplicates_unreviewed_skills_and_unknown_columns_rejected_before_calls(self):
        row = course()
        for rows, existing in (([row, deepcopy(row)], []), ([row], [row['fields']])):
            with self.assertRaisesRegex(ValueError, '중복'):
                validate_rows(rows, SKILLS, existing, now=NOW)
        row = course(); row['reviewed_skill_ids'] = [2]
        with self.assertRaisesRegex(ValueError, '스킬'):
            validate_rows([row], SKILLS, [], now=NOW)
        row = course(); row['fields']['arbitrary_sql'] = 'invalid'
        with self.assertRaisesRegex(ValueError, '필드'):
            validate_rows([row], SKILLS, [], now=NOW)

    def test_prerequisite_only_skills_not_restored_after_ai_review(self):
        row = course(); row['matches'] = {1: ['SQL']}
        row['fields']['syllabus_summary'] += ' SQL Server 실행 계획과 쿼리 성능 최적화도 학습합니다.'
        row['reviewed_skill_ids'] = [1, 2]
        conn = MagicMock()
        conn.execute.return_value.fetchall.side_effect = [SKILLS, []]
        # Only fail at vector checking, after observing the attempted rows. No DB is connected.
        with patch('src.database.ingestion.course_supplement.resource_vectors.stored', return_value={}), \
             patch('src.database.ingestion.course_supplement.resource_vectors.sources', return_value={}):
            with self.assertRaisesRegex(ValueError, '벡터'):
                insert_approved(conn, [row], SKILLS)
        mappings = [call.args[1] for call in conn.execute.call_args_list if call.args[0].startswith('INSERT INTO public.course_skills')]
        self.assertEqual(mappings, [('KOCW_1234567', 1)])
        self.assertFalse(any('DELETE' in call.args[0] or 'UPDATE public.' in call.args[0] for call in conn.execute.call_args_list))


NEW_SKILLS = [
    {'skill_id': 25, 'name': '컴퓨터 구조 & 메모리 관리'},
    {'skill_id': 26, 'name': '객체지향 설계(OOP) & 디자인 패턴'},
    {'skill_id': 27, 'name': 'RESTful API 서버 아키텍처'},
    {'skill_id': 29, 'name': '마이크로서비스(MSA) 설계'},
    {'skill_id': 30, 'name': '웹 프레임워크 (FastAPI/Django)'},
    {'skill_id': 32, 'name': '멀티스레딩 & 비동기 동시성'},
    {'skill_id': 33, 'name': '시스템 & OS 보안 강화'},
]


def external_course(source='WEB_INFLEARN'):
    row = course()
    if source == 'WEB_INFLEARN':
        url = 'https://www.inflearn.com/course/fastapi-실습?cid=123456'
        row.update(source=source, external_key='123456', reviewed_skill_ids=[30])
        row['fields'].update(course_id='INFLEARN_123456', title='FastAPI 실습', url=url, source_url=url,
                             record_source=source, cost=77000,
                             syllabus_summary='FastAPI를 이용하여 웹 서버의 요청과 응답을 처리하고 라우팅 및 데이터 검증을 구현하는 실습 과정입니다.')
        row['raw'] = dict(source_id='123456', url=url, http_status=200, metadata_exposure=True,
                          availability_basis='published_sale_offer',
                          course_info=dict(id=123456, slug='fastapi-실습', title='FastAPI 실습', status='PUBLISH',
                                           originalLanguage='KO', paymentInfo=dict(type='REGULAR_PRICE_PURCHASE', krwPaymentPrice=77000)),
                          lessons=[dict(title=t, hasVideo=True) for t in ('요청 처리', '응답 처리')])
    else:
        url = 'https://opentutorials.org/course/1234'
        row.update(source=source, external_key='1234', reviewed_skill_ids=[30])
        row['fields'].update(course_id='OPENTUTORIALS_1234', title='Django 실습', url=url, source_url=url,
                             record_source=source, cost=0,
                             syllabus_summary='파이썬 장고 웹 프레임워크를 이용하여 장고 앱을 만들고 URL 라우팅과 읽기, 생성, 수정 및 삭제 기능을 구현합니다.')
        row['raw'] = dict(source_id='1234', url=url, http_status=200, public_marker_present=True,
                          lessons=[dict(title=t, url=url + '/' + str(i), http_status=200, video_embed_present=True)
                                   for i, t in enumerate(('장고 앱', '장고 라우팅'), 1)])
    return row


class ExternalCourseTests(unittest.TestCase):
    def reason(self, row):
        return exclusion_reason('courses', row['fields'], row['source'], row['raw'], row['fetched_at'], now=NOW)

    def test_published_paid_and_free_public_courses_validate(self):
        rows = [external_course(), external_course('WEB_OPENTUTORIALS')]
        self.assertEqual(len(validate_rows(rows, NEW_SKILLS, [], now=NOW)), 2)

    def test_inflearn_requires_exact_provider_id_slug_and_title(self):
        for key, value in (('id', 99999), ('slug', '다른강좌'), ('title', '다른 제목')):
            row = external_course(); row['raw']['course_info'][key] = value
            self.assertIsNotNone(self.reason(row))
        row = external_course(); row['fields']['url'] = row['raw']['url'] = 'https://example.com/course/fastapi-실습?cid=123456'
        self.assertIsNotNone(self.reason(row))

    def test_inflearn_unpublished_hidden_or_foreign_courses_fail_closed(self):
        for key, value in (('status', 'DRAFT'), ('originalLanguage', 'EN')):
            row = external_course(); row['raw']['course_info'][key] = value
            self.assertIsNotNone(self.reason(row))
        row = external_course(); row['raw']['metadata_exposure'] = False
        self.assertIsNotNone(self.reason(row))

    def test_paid_price_is_never_replaced_by_free_or_unknown(self):
        for price in (0, None, -1, '77000'):
            row = external_course(); row['fields']['cost'] = price
            self.assertEqual(self.reason(row), 'missing_factual_inflearn_price')
        row = external_course(); row['raw']['course_info']['paymentInfo']['type'] = 'CLOSED'
        self.assertIsNotNone(self.reason(row))

    def test_genuine_discounted_and_free_offers_keep_their_official_price(self):
        for kind, price in (('DISCOUNTED_PURCHASE', 55000), ('FREE', 0)):
            row = external_course()
            row['raw']['course_info']['paymentInfo'].update(type=kind, krwPaymentPrice=price)
            row['fields']['cost'] = price
            self.assertIsNone(self.reason(row))
        row['fields']['cost'] = row['raw']['course_info']['paymentInfo']['krwPaymentPrice'] = 1000
        self.assertIsNotNone(self.reason(row))

    def test_actual_security_and_thread_course_titles_are_in_scope(self):
        for title, body in [('웹 해킹 실습', '웹 애플리케이션의 취약점을 진단하고 모의해킹으로 입력 검증과 인증 우회에 대한 보안 대책을 실습합니다.'),
                            ('Java 멀티스레드와 동기화', 'Java 프로그래밍의 멀티스레드와 동기화를 구현하고 경쟁 상태와 공유 자원에 대한 안전한 접근 제어를 실습합니다.')]:
            self.assertIsNone(scope_reason('courses', dict(title=title, syllabus_summary=body), 'WEB_INFLEARN', {}))
        self.assertEqual(scope_reason('courses', dict(title='자바섬 여행', syllabus_summary='Java 프로그램으로 여행 기록을 작성합니다.'), 'WEB_INFLEARN', {}), 'scope_outside_it_subject')

    def test_curriculum_requires_multiple_actual_video_entries(self):
        for source, flag in (('WEB_INFLEARN', 'hasVideo'), ('WEB_OPENTUTORIALS', 'video_embed_present')):
            row = external_course(source); row['raw']['lessons'][0][flag] = False
            self.assertIsNotNone(self.reason(row))

    def test_public_course_owns_its_lesson_urls(self):
        for url in ('https://example.com/course/1234/1', 'https://opentutorials.org/course/9999/1'):
            row = external_course('WEB_OPENTUTORIALS'); row['raw']['lessons'][0]['url'] = url
            self.assertIsNotNone(self.reason(row))
        row = external_course('WEB_OPENTUTORIALS'); row['raw']['public_marker_present'] = False
        self.assertIsNotNone(self.reason(row))

    def test_new_sources_also_expire_and_duplicate_before_paid_calls(self):
        for source in ('WEB_INFLEARN', 'WEB_OPENTUTORIALS'):
            row = external_course(source); row['fetched_at'] = '2026-09-01T00:00:00Z'
            self.assertEqual(self.reason(row), 'missing_or_expired_availability_evidence')
            row = external_course(source)
            with self.assertRaisesRegex(ValueError, '중복'):
                validate_rows([row], NEW_SKILLS, [row['fields']], now=NOW)
            row['external_key'] = '9999'
            with self.assertRaisesRegex(ValueError, '원본 ID'):
                validate_rows([row], NEW_SKILLS, [], now=NOW)

    def test_real_curriculum_terms_match_without_title_only_or_substrings(self):
        matcher = SkillMatcher(NEW_SKILLS)
        for sid, body in [(25, 'CPU 데이터 경로와 SRAM 및 DRAM을 구성합니다.'),
                          (26, '자바 프로그래밍에서 클래스와 객체 및 상속을 구현합니다.'),
                          (27, 'REST API와 RESTful 서비스를 구현합니다.'),
                          (29, '마이크로 서비스를 빌드하고 배포합니다.'),
                          (30, '파이썬 장고 앱과 장고 라우팅을 구현합니다.'),
                          (32, '멀티 쓰레드 실습과 ThreadPool을 구현합니다.'),
                          (33, 'Windows 보안 및 공격 표면 감소 규칙을 구성합니다.')]:
            with self.subTest(skill=sid):
                self.assertIn(sid, matcher.match(body))
        self.assertEqual(matcher.match('장고 음악과 데이터 분류표를 소개합니다.'), {})
        self.assertEqual(scoped_matches(matcher, dict(title='REST API 개발', description='일반적인 과정 소개입니다.')), {})


if __name__ == '__main__':
    unittest.main()
