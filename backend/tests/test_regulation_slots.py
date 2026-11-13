"""3-1단계의 4·2·1 슬롯 배분과 실제 부모·참조 원문 전달을 검사한다."""
from __future__ import annotations

import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app.agents import regulation as reg
from app.agents import runtime as rt


class RegulationSlotsTest(unittest.TestCase):
    def setUp(self):
        self.ctx = rt.Ctx(employee_id=1, me={'empGroup': '일반직'})
        self.current = [f'current-{index}' for index in range(1, 6)]
        self.joined = [f'joined-{index}' for index in range(1, 6)]
        self.previous = [f'previous-{index}' for index in range(1, 5)]
        self.parents = ['parent-condition', 'parent-exception']
        self.references = ['reference-1', 'reference-2']
        identifiers = self.current + self.joined + self.previous + self.parents + self.references
        self.articles = {
            aid: dict(id=aid, reg='edu', no=f'제{index + 30}조', text='등록된 원문이다.',
                      title='', chapter='', type='article', path='', parent=None, order=index,
                      group='일반직', overseas=False)
            for index, aid in enumerate(identifiers)
        }
        regs = {key: dict(key=key, name=name, version_label='test', amendment_date=None,
                          effective_from=None, file_name='', overseas_only=False,
                          employee_group='실무직' if key == 'practice' else '일반직')
                for key, name in (('edu', '인재개발규정'), ('work', '취업규칙'), ('practice', '실무직관리규정'))}
        data = {'arts': self.articles, 'regs': regs, 'sets': {}}
        for target, name, value in (
            (reg.regstore, 'data', data),
            (reg.question_classifier, 'classify', {'label': '사내 규정', 'confidence': 0.9}),
            (reg.llm, 'available', True),
        ):
            mocked = patch.object(target, name, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)

    def retrieve(self, previous_count=0, parent_ids=None, ref_ids=None):
        history = [{'q': '교육비 지원 기준은?', 'a': {'basis': self.previous[:previous_count]}}] if previous_count else []
        inp = {'question': '그럼 출장비는?', 'me': self.ctx.me, 'history': history,
               '_history': history, 'documents_only': True}
        results = [[{'id': aid} for aid in self.current]]
        if history:
            results.append([{'id': aid} for aid in self.joined])

        def supplement(candidates):
            return lambda selected, *args, limit: [aid for aid in candidates if aid not in selected][:limit]

        with (patch.object(reg.hybrid_search, 'enabled', return_value=True),
              patch.object(reg.regstore, 'explicit_ref', return_value={'ids': ref_ids} if ref_ids else None),
              patch.object(reg.regstore, 'search', side_effect=results),
              patch.object(reg.regstore, 'parent_context', side_effect=supplement(
                  self.parents if parent_ids is None else parent_ids)) as parents,
              patch.object(reg.regstore, 'referenced_paragraphs', side_effect=supplement(self.references)) as refs):
            ids = reg.retrieve_regulation_slots(self.ctx, inp)
        return ids, parents, refs

    def test_first_question_reserves_two_parent_slots_and_one_reference(self):
        ids, parents, refs = self.retrieve()
        self.assertEqual(ids, self.current[:4] + self.parents + self.references[:1])
        self.assertEqual(parents.call_args.kwargs['limit'], 2)
        self.assertEqual(refs.call_args.kwargs['limit'], 1)

    def test_follow_up_keeps_current_hits_with_one_to_four_previous_sources(self):
        for count in range(1, 5):
            with self.subTest(previous_count=count):
                ids, parents, _ = self.retrieve(previous_count=count)
                core = self.current[:2] + self.previous[:1] + self.joined[:1]
                self.assertEqual(ids, core + self.parents + self.references[:1])
                self.assertEqual(parents.call_args.args[0], core)
                self.assertEqual(set(ids) & set(self.previous), {self.previous[0]})

    def test_two_reference_candidates_do_not_displace_parent_context(self):
        ids, _, _ = self.retrieve(previous_count=4)
        self.assertTrue(set(self.parents).issubset(ids))
        self.assertIn(self.references[0], ids)
        self.assertNotIn(self.references[1], ids)
        self.assertEqual(len(ids), 7)
        self.assertEqual(len(set(ids)), 7)

    def test_missing_parents_backfills_search_but_still_adds_only_one_reference(self):
        ids, _, refs = self.retrieve(parent_ids=[])
        self.assertEqual(ids, self.current[:4] + self.references[:1] + self.current[4:])
        self.assertEqual(refs.call_args.kwargs['limit'], 1)

    def test_duplicate_candidates_and_previous_sources_do_not_waste_slots(self):
        self.current = ['current-1', 'current-1', 'current-2', 'current-3', 'current-4']
        self.previous = ['current-1', 'previous-1', 'previous-2', 'previous-3']
        ids, _, _ = self.retrieve(previous_count=4)
        self.assertEqual(ids[:2], ['current-1', 'current-2'])
        self.assertEqual(len(ids), 7)
        self.assertEqual(len(set(ids)), 7)
        self.assertNotIn('previous-2', ids)

    def test_explicit_articles_keep_priority_including_legacy_budget_exception(self):
        for count in (1, 5, 8):
            with self.subTest(explicit_count=count):
                explicit = (self.previous + self.joined)[:count]
                ids, _, _ = self.retrieve(ref_ids=explicit)
                self.assertEqual(ids[:count], explicit)
                self.assertEqual(len(ids), max(7, count))

    def real_context(self):
        # 같은 실제 조 노드의 조건·예외와 직접 참조 원문을 서로 다른 항으로 준비한다.
        for aid, number, text in (
            ('current-1', 5, '제3항부터 제4항까지의 기준에 따라 신청한다.'),
            ('parent-condition', 1, '승인된 과정에 한해 지원한다.'),
            ('parent-exception', 2, '예산 부족 시 지원 대상에서 제외한다.'),
            ('reference-1', 3, '신청서는 교육 담당 부서에 제출한다.'),
            ('reference-2', 4, '결과 보고서는 교육 담당 부서에 제출한다.'),
        ):
            self.articles[aid].update(no=f'제24조 제{number}항', text=text, type='paragraph',
                                      parent='actual-article', order=number)
        self.articles['previous-1'].update(parent='old-article', reg='work')
        self.articles['old-sibling'] = dict(self.articles['parent-condition'], id='old-sibling',
                                            reg='work', parent='old-article')
        for aid, changes in (
            ('wrong-parent', {'parent': 'different-article', 'no': '제25조 제1항'}),
            ('wrong-regulation', {'reg': 'work'}),
            ('wrong-group', {'reg': 'practice', 'group': '실무직'}),
            ('overseas', {'overseas': True}),
        ):
            self.articles[aid] = dict(self.articles['parent-condition'], id=aid, **changes)

    def test_actual_parent_and_reference_connections_isolate_scope_under_saturation(self):
        self.real_context()
        self.assertEqual(reg.regstore.referenced_paragraphs(self.current[:1], limit=2), self.references)
        history = [{'q': '교육비 지원 기준은?', 'a': {'summary': '앞 답변', 'basis': self.previous}}]
        inp = {'question': '그럼 출장비는?', 'me': self.ctx.me, 'history': history,
               '_history': history, 'documents_only': True}
        original = copy.deepcopy(inp)
        with (patch.object(reg.hybrid_search, 'enabled', return_value=True),
              patch.object(reg.regstore, 'search', side_effect=[
                  [{'id': aid} for aid in self.current], [{'id': aid} for aid in self.joined]])):
            ids = reg.retrieve_regulation_slots(self.ctx, inp)
        self.assertEqual(ids, self.current[:2] + self.previous[:1] + self.joined[:1]
                         + self.parents + self.references[:1])
        self.assertEqual(inp['history'], original['history'])
        self.assertFalse(set(ids) & {'old-sibling', 'wrong-parent', 'wrong-regulation', 'wrong-group', 'overseas'})

    def test_actual_missing_parent_and_reference_connections_backfill_current_search(self):
        inp = {'question': '교육비 지원 기준은?', 'me': self.ctx.me,
               'history': [], 'documents_only': True}
        with (patch.object(reg.hybrid_search, 'enabled', return_value=True),
              patch.object(reg.regstore, 'search', return_value=[{'id': aid} for aid in self.current])):
            ids = reg.retrieve_regulation_slots(self.ctx, inp)
        self.assertEqual(ids, self.current)

    def test_actual_context_reaches_model_and_citations_for_both_providers(self):
        self.real_context()
        for provider in ('ollama', 'openai'):
            for mode in ('hybrid', 'vector'):
                with self.subTest(provider=provider, mode=mode):
                    self.ctx.provider = provider
                    aliases = ['S005', 'S006'] if mode == 'hybrid' else ['S005']
                    summary = '승인된 과정에 한해 지원하며 예산 부족 시 제외해요.' if mode == 'hybrid' else '신청서는 교육 담당 부서에 제출해요.'
                    with (patch.dict(os.environ, ASSISTANT_SEARCH_MODE=mode),
                          patch.object(reg.regstore, 'search', return_value=[{'id': aid} for aid in self.current]),
                          patch.object(rt, '_log'),
                          patch.object(rt, 'llm_json', return_value={
                              'status': 'partial', 'summary': summary, 'sourceIds': aliases}) as model):
                        answer = reg.answer(self.ctx, '교육비 지원 기준은?', [], {}, documents_only=True)
                    sources = model.call_args.args[2]['sources']
                    if mode == 'hybrid':
                        self.assertEqual(answer['basis'], self.parents)
                        self.assertEqual(answer['retrieved'], self.current[:4] + self.parents + self.references[:1])
                        self.assertEqual([source['text'] for source in sources[4:6]],
                                         [self.articles[aid]['text'] for aid in self.parents])
                    else:
                        self.assertEqual(answer['basis'], self.references[:1])
                        self.assertFalse(set(self.parents) & set(answer['retrieved']))
                    self.assertEqual([source['id'] for source in sources],
                                     [f'S{index:03d}' for index in range(1, len(sources) + 1)])
                    self.assertTrue(set(answer['basis']).issubset(answer['retrieved']))


if __name__ == '__main__':
    unittest.main()
