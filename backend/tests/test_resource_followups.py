"""#76 카드 근거·Crash 첫 선택 회귀. 외부 연결 없이 실제 판정·일정을 사용한다."""
from copy import deepcopy
import unittest

from app.agents.resource_recommendations import recommend_resources, _finalize_crash
from app.services import crash_courses as crash
from app.services import resource_evidence as evidence
from app.services.duration_proposals import resource_schedule


def course(key, titles, hours=2, skills=None):
    return {'id': key, 'type': 'course', 'title': key, 'usable': True, 'cost': 0,
            'hours': hours, 'timeStatus': 'confirmed', 'difficulty': 'INTERMEDIATE', 'skills': skills or ['ETL'],
            'curriculum': {'items': [{'section': 'dbt', 'title': title} for title in titles]}}


class ResourceCardEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.project = {'goal': 'dbt 파이프라인 구현'}
        self.selection = {'skills': [{'name': 'ETL', 'application': 'dbt 모델·품질 테스트·증분 처리 구현'}]}

    def test_course_cards_use_server_target_gaps_for_all_tracks(self):
        row = course('partial', ['dbt 모델 실습'])
        pools = [{'name': 'ETL', 'courses': [row], 'books': []}]
        raw = {'skills': [{'name': 'ETL', 'courses': [{'id': 'partial', 'unverifiedTargetTopics': ['모델의 값']}], 'books': []}]}
        original = deepcopy((row, raw, pools))
        for pid in ('A1', 'A2', 'A3'):
            with self.subTest(course=pid):
                active = dict(row, difficulty='ADVANCED' if pid == 'A3' else 'INTERMEDIATE')
                active_pools = [{**pools[0], 'courses': [active]}]
                result = recommend_resources(self.project, self.selection, {'partial': active}, lambda *_: raw,
                                             course={'id': pid}, retrieved_pools=active_pools)
                self.assertEqual(result['skills'][0]['courses'][0]['unverifiedTargetTopics'],
                                 ['dbt 품질 테스트', 'dbt 증분 처리'])
        self.assertEqual((row, raw, pools), original)

    def test_course_cards_omit_gaps_when_fully_verified(self):
        row = course('full', ['dbt 모델 실습', 'dbt 품질 테스트 실습', 'dbt 증분 처리 구현'])
        row['unverifiedTargetTopics'] = ['이전 후보의 값']
        raw = {'skills': [{'name': 'ETL', 'courses': [{'id': 'full', 'unverifiedTargetTopics': ['모델의 값']}], 'books': []}]}
        for pid in ('A1', 'A2', 'A3'):
            with self.subTest(course=pid):
                row['difficulty'] = 'ADVANCED' if pid == 'A3' else 'INTERMEDIATE'
                result = recommend_resources(self.project, self.selection, {'full': row}, lambda *_: raw,
                                             course={'id': pid}, retrieved_pools=[{'name': 'ETL', 'courses': [row], 'books': []}])
                self.assertNotIn('unverifiedTargetTopics', result['skills'][0]['courses'][0])

    def test_shared_course_cards_keep_skill_specific_target_gaps(self):
        row = course('shared', ['dbt 모델 실습', 'SQL 조인 실습'], skills=['ETL', 'SQL'])
        selection = {'skills': [*self.selection['skills'], {'name': 'SQL', 'application': 'SQL 조인 구현'}]}
        raw = {'skills': [{'name': name, 'courses': [{'id': 'shared'}], 'books': []} for name in ('ETL', 'SQL')]}
        result = recommend_resources(self.project, selection, {'shared': row}, lambda *_: raw,
                                     course={'id': 'A2'}, retrieved_pools=[{'name': name, 'courses': [row], 'books': []} for name in ('ETL', 'SQL')])
        self.assertEqual(result['skills'][0]['courses'][0]['unverifiedTargetTopics'], ['dbt 품질 테스트', 'dbt 증분 처리'])
        self.assertNotIn('unverifiedTargetTopics', result['skills'][1]['courses'][0])


class CrashFirstChoiceTests(unittest.TestCase):
    def test_course_with_fewer_gaps_is_shared_and_counts_eight_hours_once(self):
        project = {'goal': 'dbt 파이프라인과 SQL 조인 구현'}
        selection = {'skills': [{'name': 'ETL', 'application': 'dbt 모델·품질 테스트·증분 처리 구현'},
                                {'name': 'SQL', 'application': 'SQL 조인 구현'}]}
        short = course('X', ['dbt 모델 실습', 'SQL 조인 실습'], hours=2, skills=['ETL', 'SQL'])
        long = course('L', ['dbt 모델 실습', 'dbt 품질 테스트 실습', 'SQL 조인 실습'], hours=8, skills=['ETL', 'SQL'])
        result = [{'name': 'ETL', 'courses': [long, short], 'books': [], 'selectedBooks': []},
                  {'name': 'SQL', 'courses': [deepcopy(short), deepcopy(long)], 'books': [], 'selectedBooks': []}]
        pools = deepcopy(result)
        cache = {row['id']: evidence.facts(row, project, selection) for row in (short, long)}
        _finalize_crash(result, pools, selection, project, cache)
        self.assertEqual([row['selectedCourse'] for row in result], ['L', 'L'])
        choices = {row['name']: {'course': row['selectedCourse'], 'books': []} for row in result}
        schedule = resource_schedule({'skills': result}, choices, list(choices), 4)
        self.assertEqual(set(schedule['courses']), {'L'})
        self.assertEqual(sum(row['hours'] for row in schedule['courses'].values()), 8)

    def finalize(self, long_titles, *, unsuitable=False):
        project = {'goal': 'dbt 파이프라인 구현'}
        selection = {'skills': [{'name': 'ETL', 'application': 'dbt 모델·품질 테스트·증분 처리 구현'},
                                {'name': 'SQL', 'application': 'SQL 조인 구현'},
                                {'name': 'Python', 'application': 'Python API 수집 구현'}]}
        short = course('short', ['dbt 모델 실습', 'SQL 조인 실습', 'Python API 수집 실습'], skills=['ETL', 'SQL', 'Python'])
        long = course('long', long_titles, hours=8)
        result = [{'name': 'ETL', 'courses': [long, short], 'books': [], 'selectedBooks': []},
                  *[{'name': name, 'courses': [deepcopy(short)], 'books': [], 'selectedBooks': []} for name in ('SQL', 'Python')]]
        pools = deepcopy(result)
        cache = {row['id']: evidence.facts(row, project, selection) for row in (short, long)}
        if unsuitable:
            cache['long']['suitability']['ETL']['suitable'] = False
            self.assertLess(len(evidence.target_gaps(cache['long'], 'ETL')), len(evidence.target_gaps(cache['short'], 'ETL')))
        _finalize_crash(result, pools, selection, project, cache)
        choices = {row['name']: {'course': row['selectedCourse'], 'books': []} for row in result}
        schedule = resource_schedule({'skills': result}, choices, list(choices), 4)
        self.assertEqual([card['aiRecommended'] for card in result[0]['courses']], [True, False])
        return result, schedule

    def test_returned_course_with_fewer_gaps_is_kept_and_duration_uses_unique_ids(self):
        result, schedule = self.finalize(['dbt 모델 실습', 'dbt 품질 테스트 실습'])
        self.assertEqual(result[0]['selectedCourse'], 'long')
        self.assertEqual(sum(row['hours'] for row in schedule['courses'].values()), 10)
        self.assertEqual(set(schedule['courses']), {'long', 'short'})

    def test_equal_or_more_gaps_use_shortest_bundle(self):
        for titles in (['dbt 모델 실습'], ['dbt 설치 실습']):
            with self.subTest(titles=titles):
                result, schedule = self.finalize(titles)
                self.assertEqual(result[0]['selectedCourse'], 'short')
                self.assertEqual(set(schedule['courses']), {'short'})

    def test_unsuitable_returned_course_uses_shortest_bundle(self):
        result, schedule = self.finalize(['dbt 모델 실습', 'dbt 품질 테스트 실습'], unsuitable=True)
        self.assertEqual(result[0]['selectedCourse'], 'short')
        self.assertEqual(set(schedule['courses']), {'short'})

    def recommend(self, raw_courses, diagnostic=None):
        project = {'goal': 'dbt 파이프라인 구현'}
        selection = {'skills': [{'name': 'ETL', 'application': 'dbt 모델 구현'}]}
        rows = [course('default', ['dbt 모델 실습'], hours=1), course('mid', ['dbt 모델 실습'], hours=5),
                course('long', ['dbt 모델 실습'], hours=20)]
        row = {'name': 'ETL', 'courses': [{'id': rid} for rid in raw_courses], 'books': []}
        if diagnostic:
            row['courseDiagnostic'] = {'reason': diagnostic, 'detail': '기본안은 주제가 다릅니다.'}
        return recommend_resources(project, selection, {card['id']: card for card in rows}, lambda *_: {'skills': [row]},
                                   course={'id': 'A2'}, retrieved_pools=[{'name': 'ETL', 'courses': rows, 'books': []}])['skills'][0]

    def test_server_picks_shortest_returned_course_regardless_of_order_and_reason(self):
        skill = self.recommend(['long', 'mid'], 'longer_for_coverage')
        self.assertEqual(skill['selectedCourse'], 'mid')
        self.assertEqual([card['id'] for card in skill['courses']], ['mid', 'long'])
        self.assertEqual([card['aiRecommended'] for card in skill['courses']], [True, False])
        self.assertEqual(skill['courseDiagnostic']['reason'], 'longer_for_coverage')

    def test_single_returned_longer_course_is_kept_with_its_reason(self):
        skill = self.recommend(['long'], 'longer_for_coverage')
        self.assertEqual(skill['selectedCourse'], 'long')
        self.assertEqual(skill['courseDiagnostic']['reason'], 'longer_for_coverage')

    def test_longer_reason_is_removed_when_the_default_course_is_selected(self):
        skill = self.recommend(['long', 'default'], 'longer_for_coverage')
        self.assertEqual(skill['selectedCourse'], 'default')
        self.assertNotIn('courseDiagnostic', skill)

    def test_other_reason_stays_when_the_default_course_is_selected(self):
        skill = self.recommend(['default'], 'scope_gap')
        self.assertEqual(skill['selectedCourse'], 'default')
        self.assertEqual(skill['courseDiagnostic']['reason'], 'scope_gap')

    def test_server_prefers_one_shared_course_over_two_shorter_courses(self):
        project = {'goal': 'dbt 파이프라인과 SQL 조인 구현'}
        selection = {'skills': [{'name': 'ETL', 'application': 'dbt 모델 구현'}, {'name': 'SQL', 'application': 'SQL 조인 구현'}]}
        shared = course('shared', ['dbt 모델 실습', 'SQL 조인 실습'], hours=6, skills=['ETL', 'SQL'])
        etl = course('etl', ['dbt 모델 실습'], hours=4)
        sql = course('sql', ['SQL 조인 실습'], hours=4, skills=['SQL'])
        raw = {'skills': [{'name': 'ETL', 'courses': [{'id': 'etl'}, {'id': 'shared'}], 'books': []},
                          {'name': 'SQL', 'courses': [{'id': 'sql'}, {'id': 'shared'}], 'books': []}]}
        result = recommend_resources(project, selection, {card['id']: card for card in (shared, etl, sql)}, lambda *_: raw, course={'id': 'A2'},
                                     retrieved_pools=[{'name': 'ETL', 'courses': [etl, shared], 'books': []},
                                                      {'name': 'SQL', 'courses': [sql, shared], 'books': []}])
        self.assertEqual([skill['selectedCourse'] for skill in result['skills']], ['shared', 'shared'])

    def test_bundle_keeps_fewest_gaps_when_no_course_is_complete(self):
        project = {'goal': 'dbt 파이프라인 구현'}
        selection = {'skills': [{'name': 'ETL', 'application': 'dbt 모델·품질 테스트·증분 처리 구현'}]}
        partial = course('partial', ['dbt 모델 실습'], hours=1)
        better = course('better', ['dbt 모델 실습', 'dbt 품질 테스트 실습'], hours=9)
        cache = {row['id']: evidence.facts(row, project, selection) for row in (partial, better)}
        self.assertLess(len(evidence.target_gaps(cache['better'], 'ETL')), len(evidence.target_gaps(cache['partial'], 'ETL')))
        self.assertTrue(evidence.target_gaps(cache['better'], 'ETL'))
        chosen = crash.shortest_bundle([{'name': 'ETL', 'courses': [partial, better]}], project, selection, cache)
        self.assertEqual(chosen['ETL']['id'], 'better')
