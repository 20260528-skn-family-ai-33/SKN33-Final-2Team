from copy import deepcopy
from datetime import datetime, timezone
import unittest
from urllib.parse import urlencode

from src.shared.catalog_eligibility import exclusion_reason
from src.shared.course_sources import step_reason, kmooc_reason, source_time
from src.shared.skill_matching import SkillMatcher
from src.database.ingestion.course_supplement import validate_rows, validate_catalog, canonical_url

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)
SKILLS = [{'skill_id': 1, 'name': 'SQL 기본 문법 & 조인'},
          {'skill_id': 8, 'name': '머신러닝 지도/비지도 학습'},
          {'skill_id': 22, 'name': 'Python 프로그래밍 & 비동기 I/O'},
          {'skill_id': 26, 'name': '객체지향 설계(OOP) & 디자인 패턴'},
          {'skill_id': 30, 'name': '웹 프레임워크 (FastAPI/Django)'},
          {'skill_id': 32, 'name': '멀티스레딩 & 비동기 동시성'}]


def new_course(source='WEB_STEP', *, audit=False, course_seq='22'):
    raw = dict(crscd='11', crsseqId=course_seq, dgrId='33', dgrSeCd='03', verCd='v1',
               crsNm='SQL 데이터베이스 실습', orgnztNm='교육기관', educst='77,000',
               crsregStrtdt='20261001000000', crsregEnddt='20261130235959')
    url = 'https://www.step.or.kr/dtyCrsDetailForm.do?' + urlencode({k: raw[k] for k in
          ('crscd', 'crsseqId', 'dgrId', 'dgrSeCd', 'verCd')})
    rid, external = 'STEP_11_' + course_seq, '11_' + course_seq
    start, end = '2026-09-30T15:00:00+00:00', '2026-11-30T14:59:59+00:00'
    if source == 'API_KMOOC':
        rid, external = 'KMOOC_123', '123'
        url = 'https://www.kmooc.kr/view/course/detail/123'
        start = '2026-10-01T00:00:00+00:00'
        end = '2026-10-20T00:00:00+00:00' if audit else '2026-11-30T00:00:00+00:00'
        raw = dict(id='123', name='SQL 데이터베이스 실습', org_name='교육기관', public_yn='Y',
                   is_auditor='Y' if audit else 'N', classfy_name='공학', middle_classfy_name='컴퓨터',
                   enrollment_start=str(int(datetime.fromisoformat(start).timestamp())),
                   enrollment_end=str(int(datetime.fromisoformat(end).timestamp())),
                   study_end='1798675200')
    fields = dict(course_id=rid, title='SQL 데이터베이스 실습', org_name='교육기관', platform='교육사이트',
                  url=url, source_url=url, record_source=source, source_verified_at=NOW,
                  syllabus_summary='SQL과 관계형 데이터베이스의 테이블을 설계하고 조인과 서브쿼리를 직접 작성하는 실습 과정입니다.',
                  cost=0 if source == 'API_KMOOC' else 77000, content_status='ready',
                  duration_weeks=None, enrollment_start=start, enrollment_end=end,
                  enrollment_period_type='scheduled', recruitment_status='CLOSED' if audit else 'OPEN')
    raw['public_detail'] = dict(course_id=rid, title=fields['title'], url=url, fetched_at=NOW,
        html_sha256='a'*64, curriculum_titles=['SQL SELECT 실습', 'JOIN 작성 실습'],
        audit_action_present=audit, enroll_action_present=True, public_page_title_matches=True)
    return dict(source=source, external_key=external, fields=fields, raw=raw,
                fetched_at=NOW, reviewed_skill_ids=[1])


class CourseSourceTests(unittest.TestCase):
    def test_kmooc_seconds_and_milliseconds_have_identical_availability(self):
        for with_detail in (False, True):
            row = new_course('API_KMOOC')
            if not with_detail:
                row['raw'].pop('public_detail', None)
            millis = deepcopy(row)
            for name in ('enrollment_start', 'enrollment_end', 'study_end'):
                millis['raw'][name] = str(int(millis['raw'][name]) * 1000)
            self.assertIsNone(kmooc_reason(row['fields'], row['raw'], NOW))
            self.assertIsNone(kmooc_reason(millis['fields'], millis['raw'], NOW))
            for name in ('enrollment_start', 'enrollment_end', 'study_end'):
                self.assertEqual(source_time(row['raw'][name]), source_time(millis['raw'][name]))

    def test_millisecond_parser_preserves_step_and_invalid_input_rules(self):
        seconds = 1790812800
        self.assertEqual(source_time(seconds), source_time(str(seconds * 1000)))
        self.assertEqual(source_time(str(seconds * 1000 + 123)).microsecond, 123000)
        self.assertEqual(source_time('20261001000000', step=True).isoformat(),
                         '2026-09-30T15:00:00+00:00')
        for bad in (None, '', 'not-a-date', '123456789012', '2026-10-01'):
            self.assertIsNone(source_time(bad))

    def test_public_page_title_spacing_is_not_a_false_mismatch(self):
        from scripts.prepare_course_expansion import public_title_matches
        self.assertTrue(public_title_matches('  소프트웨어  설계와 파이썬 ', '강좌 소개 소프트웨어 설계와 파이썬 강의계획'))
        self.assertFalse(public_title_matches('소프트웨어 설계와 파이썬', '다른 파이썬 강좌'))
        self.assertFalse(public_title_matches('   ', '강좌 소개'))

    def test_step_current_offer_validates_real_period_and_price(self):
        self.assertEqual(len(validate_rows([new_course()], SKILLS, [], now=NOW)), 1)

    def test_step_missing_price_is_not_free(self):
        for price in (None, '', '미정', '-1'):
            row = new_course(); row['raw']['educst'] = price
            self.assertEqual(step_reason(row['fields'], row['raw'], NOW), 'missing_factual_step_price')
        row = new_course(); row['fields']['cost'] = 0
        self.assertEqual(step_reason(row['fields'], row['raw'], NOW), 'missing_factual_step_price')

    def test_step_current_window_and_actual_dates_cannot_be_changed(self):
        for field, value in [('enrollment_end', '2030-01-01T00:00:00Z'), ('recruitment_status', 'CLOSED')]:
            row = new_course(); row['fields'][field] = value
            self.assertEqual(step_reason(row['fields'], row['raw'], NOW), 'step_not_confirmed_open')
        row = new_course(); row['raw']['crsregEnddt'] = '20261020235959'
        self.assertEqual(step_reason(row['fields'], row['raw'], NOW), 'step_not_confirmed_open')

    def test_step_distinct_offerings_and_reordered_duplicate_urls(self):
        first, second = new_course(), new_course(course_seq='23')
        self.assertEqual(len(validate_rows([first, second], SKILLS, [], now=NOW)), 2)
        reordered = first['fields']['url'].split('?')[0] + '?' + '&'.join(reversed(first['fields']['url'].split('?')[1].split('&')))
        self.assertEqual(canonical_url(reordered), canonical_url(first['fields']['url']))
        duplicate = deepcopy(first); duplicate['fields']['course_id'] = 'DIFFERENT_ID'
        duplicate['fields']['url'] = reordered
        with self.assertRaisesRegex(ValueError, '중복'):
            validate_rows([first, duplicate], SKILLS, [], now=NOW)

    def test_step_identity_rejects_other_host_id_title_and_price_override(self):
        for field, value in [('course_id', 'STEP_11_99'), ('title', '다른 SQL 강좌'),
                             ('url', 'https://example.com/dtyCrsDetailForm.do?crscd=11&crsseqId=22')]:
            row = new_course(); row['fields'][field] = value
            with self.assertRaises(ValueError):validate_rows([row], SKILLS, [], now=NOW)

    def test_new_detail_evidence_expires_or_requires_curriculum(self):
        for source in ('WEB_STEP', 'API_KMOOC'):
            for key, value in [('fetched_at', '2026-09-01T00:00:00Z'), ('curriculum_titles', ['한 차시']),
                               ('html_sha256', 'missing'), ('title', '다른 제목')]:
                row = new_course(source); row['raw']['public_detail'][key] = value
                self.assertIsNotNone(exclusion_reason('courses',row['fields'],source,row['raw'],NOW,now=NOW))

    def test_kmooc_current_and_ended_auditable_courses_are_distinct(self):
        for audit in (False, True):
            row = new_course('API_KMOOC', audit=audit)
            self.assertEqual(len(validate_rows([row], SKILLS, [], now=NOW)), 1)
            if audit:
                self.assertEqual(row['fields']['recruitment_status'], 'CLOSED')
                self.assertLess(datetime.fromisoformat(row['fields']['enrollment_end']), NOW)

    def test_audit_metadata_alone_missing_button_and_fake_open_dates_fail(self):
        for key, value in [('audit_action_present', False), ('public_page_title_matches', False)]:
            row = new_course('API_KMOOC', audit=True); row['raw']['public_detail'][key] = value
            self.assertEqual(kmooc_reason(row['fields'],row['raw'],NOW), 'course_not_confirmed_open')
        row = new_course('API_KMOOC', audit=True); del row['raw']['public_detail']
        self.assertEqual(kmooc_reason(row['fields'],row['raw'],NOW), 'course_not_confirmed_open')
        row = new_course('API_KMOOC', audit=True); row['fields']['recruitment_status'] = 'OPEN'
        self.assertEqual(kmooc_reason(row['fields'],row['raw'],NOW), 'course_not_confirmed_open')
        row = new_course('API_KMOOC', audit=True); row['fields']['enrollment_end'] = '2030-01-01T00:00:00Z'
        self.assertEqual(kmooc_reason(row['fields'],row['raw'],NOW), 'kmooc_period_mismatch')

    def test_correct_curriculum_terms_and_ambiguous_topics_are_separated(self):
        matcher = SkillMatcher(SKILLS)
        for sid, body in [(8, '선형회귀 및 소프트맥스 회귀분석을 구현합니다.'),
                          (26, 'Java 프로그래밍에서 객체 지향과 클래스 상속을 학습합니다.'),
                          (32, 'JavaScript 비동기 프로그래밍: Promise, async/await 실습')]:
            self.assertIn(sid, matcher.match(body))
        self.assertNotIn(22, matcher.match('JavaScript 비동기 프로그래밍: Promise, async/await 실습'))
        self.assertNotIn(32, matcher.match('데이터베이스의 트랜잭션과 동시성 제어 및 격리 수준을 분석합니다.'))
        self.assertNotIn(30, matcher.match('Ruby on Rails 웹 프레임워크로 게시판을 개발합니다.'))
        self.assertNotIn(26, matcher.match('객체 지향형 도면해독과 기계 제도 및 KS 치수를 학습합니다.'))

    def test_held_rows_never_reach_paid_review(self):
        row = new_course(); row['fields']['content_status'] = 'needs_review'
        with self.assertRaisesRegex(ValueError, 'not_ready'):
            validate_rows([row], SKILLS, [], now=NOW)

    def test_catalog_cap_and_cross_block_duplicate_detection(self):
        rows = [new_course(course_seq=str(i)) for i in range(1, 52)]
        self.assertEqual(len(validate_catalog(rows, SKILLS, [], max_courses=51, now=NOW)), 51)
        with self.assertRaisesRegex(ValueError, '심사 범위'):
            validate_catalog(rows, SKILLS, [], max_courses=50, now=NOW)
        rows[-1] = deepcopy(rows[0])
        with self.assertRaisesRegex(ValueError, '중복'):
            validate_catalog(rows, SKILLS, [], max_courses=51, now=NOW)
        for cap in (True, 0, 2501):
            with self.assertRaises(ValueError):validate_catalog(rows, SKILLS, [], max_courses=cap, now=NOW)


if __name__ == '__main__':
    unittest.main()
