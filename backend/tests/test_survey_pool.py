"""#225 진단 설문 사전 생성 풀: 풀 문항 검사·스킬 수별 개수·설문 중 퀴즈 생성·풀 누락 시 모델 대체."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import test_generation_concurrency as concurrency
import test_survey_generation as fixture
from test_issue67_scenarios import SurveyMemory
from app.routers import preassessment as api
from app.services import survey_pool, survey_store as store


def pool_item(name):
    return {'title': f'{name} 활용을 점검해 볼까요',
            'surveys': [f'{name} 풀 문항 {j + 1}의 조건을 설명할 수 있다.' for j in range(5)]}


class PoolMemory(SurveyMemory):
    """설문 풀 표가 있는 DB. pool 에 든 스킬만 풀 문항이 있다. can_read=False 면 표는 있으나 앱 계정에 SELECT 권한이 없다."""
    def __init__(self, draft, pool, can_read=True):
        super().__init__(draft)
        self.pool = pool
        self.can_read = can_read

    def val(self, sql, **params):
        return self.can_read if 'has_table_privilege' in sql else None

    def all(self, sql, **params):
        if 'skill_survey_pool' in sql and not self.can_read:
            raise AssertionError('permission denied for table skill_survey_pool')
        return [{'name': name, **self.pool[name]} for name in params['names'] if name in self.pool]


class CleanTests(TestCase):
    def test_accepts_five_distinct_statements(self):
        item = survey_pool.clean('Python', {'title': ' 코드를 다뤄볼까요 ', 'surveys': [{'text': f'문항 {i}'} for i in range(5)]})
        self.assertEqual(item['title'], '코드를 다뤄볼까요')
        self.assertEqual(item['surveys'], [f'문항 {i}' for i in range(5)])

    def test_rejects_wrong_count_duplicates_and_tag_title(self):
        cases = [{'title': '제목', 'surveys': ['a', 'b', 'c', 'd']},
                 {'title': '제목', 'surveys': ['a', 'b', 'c', 'd', ' A ']},
                 {'title': 'Python', 'surveys': ['a', 'b', 'c', 'd', 'e']},
                 {'title': '제목', 'surveys': ['a', 'b', 'c', 'd', '']},
                 ['not', 'a', 'dict']]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(survey_pool.PoolError):
                survey_pool.clean('Python', raw)


class SurveysForTests(TestCase):
    def test_three_per_skill_for_many_and_five_for_one(self):
        memory = PoolMemory({}, {'A': pool_item('A'), 'B': pool_item('B')})
        two = survey_pool.surveys_for(memory, {'skills': [{'name': 'A'}, {'name': 'B'}]})
        self.assertEqual([g['skill'] for g in two['groups']], ['A', 'B'])
        self.assertTrue(all(len(g['surveys']) == 3 and g['quizzes'] == [] for g in two['groups']))
        self.assertEqual(two['groups'][0]['surveys'][0]['text'], pool_item('A')['surveys'][0])
        one = survey_pool.surveys_for(memory, {'skills': [{'name': 'A'}]})
        self.assertEqual(len(one['groups'][0]['surveys']), 5)

    def test_missing_skill_or_table_returns_none(self):
        memory = PoolMemory({}, {'A': pool_item('A')})
        self.assertIsNone(survey_pool.surveys_for(memory, {'skills': [{'name': 'A'}, {'name': 'B'}]}))
        self.assertIsNone(survey_pool.surveys_for(SurveyMemory({}), {'skills': [{'name': 'A'}]}))
        self.assertIsNone(survey_pool.surveys_for(memory, {'skills': []}))

    def test_unreadable_pool_returns_none_without_querying(self):
        memory = PoolMemory({}, {'A': pool_item('A')}, can_read=False)
        self.assertIsNone(survey_pool.surveys_for(memory, {'skills': [{'name': 'A'}]}))


class StagedPoolTests(TestCase):
    setUp = concurrency.GenerationConcurrencyTests.setUp

    def run_staged(self, memory, project, f, names, calls, started=None, release=None):
        @contextmanager
        def transaction():
            yield memory

        def model(ctx, system, payload, **kwargs):
            phase = 'surveys' if payload['surveysPerSkill'] else 'quizzes'
            calls.append(phase)
            if phase == 'quizzes' and started is not None:
                started.set()
                if not release.wait(5):
                    raise AssertionError('quiz barrier timeout')
            result = f.result(len(names))
            for group in result['groups']:
                group['quizzes' if phase == 'surveys' else 'surveys'] = []
                for q in group['quizzes']:
                    q.update(concept=q['q'], questionType='오류 원인 판단', difficulty='적용')
            return result

        return (patch.object(api.db, 'tx', side_effect=transaction), patch.object(api, 'project_input', return_value=project),
                patch.object(api.profile, 'view', return_value=f.profile), patch.object(api, 'profile_input', side_effect=lambda x: x),
                patch('app.catalog.skill_names', return_value=names), patch.object(api.runtime, 'context', return_value=SimpleNamespace(live=True)),
                patch.object(api.runtime, 'llm_json', side_effect=model))

    def setup_case(self, count, pool_names, can_read=True):
        f = fixture.SurveyTests()
        f.setUp()
        project = {k: v for k, v in f.project.items() if k != 'rawText'}
        project['selectedSkills'] = f.selection(count)['skills']
        names = [row['name'] for row in project['selectedSkills']]
        memory = PoolMemory({'goal': project['goal']}, {name: pool_item(name) for name in names if name in pool_names}, can_read)
        return f, project, names, memory

    def generate(self, memory, project, f, names):
        calls = []
        patches = self.run_staged(memory, project, f, names, calls)
        for p in patches:
            p.start()
        try:
            return api.generate_for(1, 'p', staged=True), calls
        finally:
            for p in patches:
                p.stop()

    def test_pool_surveys_shown_while_quizzes_generate(self):
        f, project, names, memory = self.setup_case(2, {'스킬0', '스킬1'})
        started, release, calls = Event(), Event(), []
        patches = self.run_staged(memory, project, f, names, calls, started, release)
        for p in patches:
            p.start()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                job = pool.submit(api.generate_for, 1, 'p', staged=True)
                try:
                    self.assertTrue(started.wait(3))
                    partial = store.read(memory, 1, 'p')
                    self.assertEqual(partial['quizStatus'], 'pending')
                    groups = partial['survey']['groups']
                    self.assertEqual([[q['text'] for q in g['surveys']] for g in groups],
                                     [pool_item(name)['surveys'][:3] for name in names])
                    self.assertTrue(all(not g['quizzes'] for g in groups))
                    answers = {q['id']: 4 for g in groups for q in g['surveys']}
                    store.save_answers(memory, 1, 'p', partial['generationId'], answers, complete=False)
                finally:
                    release.set()
                final = job.result(timeout=5)
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(calls, ['quizzes'])
        self.assertEqual(final['quizStatus'], 'ready')
        self.assertEqual(final['answers'], answers)
        self.assertTrue(all(len(g['surveys']) == 3 and len(g['quizzes']) == 3 for g in final['groups']))

    def test_single_skill_uses_five_pool_surveys(self):
        f, project, names, memory = self.setup_case(1, {'스킬0'})
        calls = []
        patches = self.run_staged(memory, project, f, names, calls)
        for p in patches:
            p.start()
        try:
            final = api.generate_for(1, 'p', staged=True)
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(calls, ['quizzes'])
        self.assertEqual([q['text'] for q in final['groups'][0]['surveys']], pool_item('스킬0')['surveys'])
        self.assertEqual(len(final['groups'][0]['quizzes']), 5)

    def test_partial_pool_falls_back_to_model_surveys(self):
        f, project, names, memory = self.setup_case(2, {'스킬0'})
        calls = []
        patches = self.run_staged(memory, project, f, names, calls)
        for p in patches:
            p.start()
        try:
            final = api.generate_for(1, 'p', staged=True)
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(calls, ['surveys', 'quizzes'])
        self.assertEqual(final['quizStatus'], 'ready')

    def test_pool_without_select_privilege_falls_back_then_reads_after_grant(self):
        # 마이그레이션 계정과 앱 계정이 달라 SELECT 권한이 없으면 모델 생성, 권한을 주면 풀 문항을 읽는다.
        f, project, names, memory = self.setup_case(2, {'스킬0', '스킬1'}, can_read=False)
        final, calls = self.generate(memory, project, f, names)
        self.assertEqual(calls, ['surveys', 'quizzes'])
        self.assertEqual(final['quizStatus'], 'ready')

        f, project, names, memory = self.setup_case(2, {'스킬0', '스킬1'}, can_read=True)
        final, calls = self.generate(memory, project, f, names)
        self.assertEqual(calls, ['quizzes'])
        self.assertEqual([[q['text'] for q in g['surveys']] for g in final['groups']],
                         [pool_item(name)['surveys'][:3] for name in names])
