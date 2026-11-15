"""수정안을 생성하는 시점에 새 강좌의 가격을 검사한다. DB와 외부 모델은 호출하지 않는다."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from app import catalog, catalog_budget, llm
from app.agents import roadmap
from app.free_track import validate_free_plan


def course(key, title, price):
    return dict(id=key, title=title, cost=price, hours=2, format='영상', kind='강좌', type='course',
                stage=2, skills=['SQL'], usable=True, content='SQL 조인 실습')


class ZeroBudgetRevisionTests(TestCase):
    def setUp(self):
        self.items = {r['id']: r for r in [
            course('old', '기존 SQL 강좌', 48000), course('paid', 'A SQL 강좌', 48000),
            course('unknown', 'B SQL 강좌', None), course('free', 'Z SQL 강좌', 0),
        ]}
        self.items['book'] = dict(course('book', 'C SQL 도서', 22000), type='book', kind='도서')
        self.items['old']['format'] = '문서'
        self.original = dict(id='old-act', title='기존 SQL 강좌', skill='SQL', stage=2, res='old', hours=2, how='학습')
        self.enterContext(patch.object(catalog, 'items', return_value=self.items))
        self.enterContext(patch.object(catalog, 'skill_names', return_value=['SQL']))
        self.enterContext(patch.object(catalog_budget, 'tokens', return_value=1))
        self.enterContext(patch.object(roadmap, '_sys', return_value='revision'))

    def generate(self, track, budget, changes, model=None):
        plan = dict(opt=track, name=track, tagline='SQL', hours=4, start=1, acts=[self.original], **{'def': {}})
        handoff = dict(goal='SQL 조인 실습', skillNames=['SQL'], startStage=1,
                       resourceHints=['unknown'], selectedResourceIds=['paid', 'old'],
                       prefs=dict(budgetWon=budget, weeklyHours=4, formatKey='video'))
        def dispatch(ctx, agent, task, data, mock, live, **kwargs):
            return mock(data) if model is None else live(data)
        with patch.object(roadmap.rt, 'run', side_effect=dispatch), patch.object(roadmap.rt, 'llm_json', side_effect=model):
            return roadmap.revise(SimpleNamespace(mode='openai'), dict(pid=track, plan=plan, handoff=handoff, changes=changes))

    def test_mock_replacement_and_format_changes_choose_free_course(self):
        for track in ('A2', 'A3'):
            for budget in (0, '0'):
                for changes in ({'replaceActs': [{'key': 'old-act', 'title': '기존 SQL 강좌'}]},
                                {'format': '영상으로 학습'}):
                    with self.subTest(track=track, budget=budget, changes=changes):
                        proposal = self.generate(track, budget, changes)
                        self.assertEqual([a['res'] for a in proposal['acts']], ['free'])
                        prior = {'acts': [self.original]}
                        plan = roadmap.build_plan(roadmap.keep_ids(proposal, prior, 2), {'hours': 4}, 'SQL')
                        tx = Mock()
                        tx.all.return_value = [dict(resource_key='free', resource_type='course', cost_won=0)]
                        validate_free_plan(tx, plan, budget=budget, previous=prior)
                        self.assertEqual(plan['cost'], 0)

    def test_no_free_alternative_retains_original_and_explains_why(self):
        del self.items['free']
        for track in ('A2', 'A3'):
            with self.subTest(track=track):
                proposal = self.generate(track, 0, {'replaceActs': [{'key': 'old-act', 'title': '기존 SQL 강좌'}]})
                self.assertEqual([a['res'] for a in proposal['acts']], ['old'])
                self.assertTrue(any('무료 강좌' in note and '유지' in note for note in proposal['notes']))

    def test_model_candidates_filter_before_limit_and_keep_current_activity_separate(self):
        for i in range(24):
            self.items[str(i)] = course(str(i), f'AAA SQL 조인 {i:02}', 5000)
        for track in ('A2', 'A3'):
            for budget in (0, '0', None, 50000):
                def model(ctx, system, data, **kwargs):
                    ids = {r['id'] for r in data['catalog']}
                    if budget in (0, '0'):
                        self.assertIn('free', ids)
                        self.assertIn('book', ids)
                        self.assertFalse(any(self.items[key]['type'] == 'course' and self.items[key]['cost'] != 0 for key in ids))
                    else:
                        self.assertIn('paid', ids)
                    old = data['current']['acts'][0]
                    self.assertEqual((old['key'], old['res']), ('old-act', 'old'))
                    return {'acts': [old]}
                with self.subTest(track=track, budget=budget):
                    result = self.generate(track, budget, {'weeklyHours': 6}, model)
                    self.assertEqual([a['res'] for a in result['acts']], ['old'])

    def test_model_cannot_publish_new_paid_unknown_or_duplicate_old_course(self):
        for track in ('A2', 'A3'):
            for new_id in ('paid', 'unknown', 'old'):
                def model(ctx, system, data, **kwargs):
                    old = deepcopy(data['current']['acts'][0])
                    return {'acts': [old, dict(old, key=None, res=new_id)]}
                with self.subTest(track=track, new_id=new_id), self.assertRaisesRegex(llm.LlmError, '예산 0원'):
                    self.generate(track, 0, {}, model)
