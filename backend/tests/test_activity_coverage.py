from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch

from app import catalog
from app.agents import roadmap
from app.errors import ApiError
from app.services import activity_selection as activities


class ReviewActivityCoverageTests(TestCase):
    def setUp(self):
        self.skills = ['머신러닝 지도/비지도 학습', '탐색적 데이터 분석(EDA) & 전처리', 'Python 프로그래밍 & 비동기 I/O']
        self.choices = {}
        resources = {}
        rows = []
        for i, name in enumerate(self.skills):
            course = dict(id=f'c{i}', type='course', title=f'강좌 {i}', cost=9000 if i == 1 else 0, hours=4)
            book = dict(id=f'b{i}', type='book', title=f'도서 {i}', cost=None, hours=10)
            resources.update({course['id']: course, book['id']: book})
            self.choices[name] = {'course': course['id'], 'books': [book['id']]}
            rows.append({'name': name, 'courses': [course], 'books': [book]})
        self.saved = {'generationId': 'g', 'project': {'goal': '수질 측정 자료의 분리 방식별 분류 성능 비교'},
                      'skillOrder': self.skills, 'resourceChoices': self.choices,
                      'recommendations': {'id': 'r', 'skills': rows}}
        self.draft = {'chosen': 'A2', 'handoff': {'key': 'h', 'startStage': 3, 'prefs': {'weeklyHours': 4}},
                      'gen': {'options': {'A2': {'id': 'A2', 'weeklyHours': 4}}}}
        self.tasks = [dict(skill=name, stage=2, title=f'{name} 적용 과제', how='실험 결과와 재현 절차를 제출한다.',
                           hours=2, res=None) for name in self.skills]
        self.summaries = {name: ['데이터 준비', '실험 재현', '결과 비교'] for name in self.skills}
        self.enterContext(patch.object(catalog, 'items', return_value=resources))
        self.enterContext(patch.object(catalog, 'skill_names', return_value=self.skills))

    def test_three_tasks_six_materials_reach_final_plan_in_one_model_call(self):
        model = Mock(return_value={'skillSummaries': self.summaries, 'acts': self.tasks})
        proposal = activities.propose(self.saved, self.draft, model, 'test')
        model.assert_called_once()
        activities.append_proposal(self.saved, self.draft, proposal)
        selected = activities.selection_option(self.saved, self.draft, proposal['selectedIds'])
        plan = roadmap.build_plan(selected, roadmap.params_of(self.draft['handoff'], selected), self.saved['project']['goal'])
        self.assertEqual(len(plan['acts']), 9)
        self.assertEqual(len(set(proposal['selectedIds'])), 9)
        for i, skill in enumerate(self.skills):
            self.assertEqual([a['res'] for a in plan['acts'] if a['skill'] == skill], [f'c{i}', f'b{i}', None])
        self.assertEqual((plan['weeks'], plan['materialHours'], plan['taskHours'], plan['totalH']), (3, 12, 6, 18))
        self.assertEqual(plan['cost'], 9000)

    def test_repairs_only_missing_task_without_changing_previous_response(self):
        missing = self.skills[-1]
        first = {'skillSummaries': self.summaries, 'acts': self.tasks[:-1]}
        before = deepcopy(first)
        model = Mock(side_effect=[first, {'acts': [self.tasks[-1]]}])
        proposal = activities.propose(self.saved, self.draft, model, 'test')
        self.assertEqual(first, before)
        self.assertEqual(model.call_count, 2)
        retry = model.call_args.args[1]
        self.assertEqual(retry['skillOrder'], [missing])
        self.assertEqual(list(retry['choices']), [missing])
        self.assertEqual([row['id'] for row in retry['materials']], ['c2', 'b2'])
        self.assertEqual([act['title'] for act in proposal['option']['acts'] if not act['res']],
                         [task['title'] for task in self.tasks])
        self.assertEqual(proposal['skillSummaries'], self.summaries)

    def test_unsuccessful_repair_identifies_missing_skill_and_stops(self):
        model = Mock(side_effect=[{'skillSummaries': self.summaries, 'acts': self.tasks[:-1]}, {'acts': []}])
        with self.assertRaises(ApiError) as error:
            activities.propose(self.saved, self.draft, model, 'test')
        self.assertEqual(error.exception.code, 'ACTIVITIES_INVALID')
        self.assertIn(self.skills[-1], error.exception.message)
        self.assertEqual(model.call_count, 2)
        self.assertNotIn('activityProposal', self.saved)
