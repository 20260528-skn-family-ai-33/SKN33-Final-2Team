"""가짜 규정과 모의 모델로 조항 이어 묻기·이전 답변 전달의 회귀를 검사한다."""
from __future__ import annotations

import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app.agents import regulation as reg
from app.agents import runtime as rt
from app.llm import LlmError


class RegulationFollowUpTest(unittest.TestCase):
    def setUp(self):
        self.ctx = rt.Ctx(employee_id=1, me={'empGroup': '일반직'})
        regs = [{'key': 'edu', 'name': '인재개발규정'}, {'key': 'work', 'name': '취업규칙'}]
        for item in regs:
            item.update(version_label='test', amendment_date=None, effective_from=None,
                        file_name='', employee_group='일반직', overseas_only=False)
        self.articles = {}
        for key, no, text in [('edu', 7, '학습시간을 인정한다.'), ('edu', 9, '교육 신청은 교육포털에서 한다.'),
                              ('work', 2, '직원에게 적용한다.'), ('work', 9, '근무를 기록한다.')]:
            aid = f'{key}-{no}'
            self.articles[aid] = {'id': aid, 'reg': key, 'no': f'제{no}조', 'text': text,
                                  'title': '', 'chapter': '', 'type': 'article', 'path': ''}
        data = {'regs': {item['key']: item for item in regs}, 'arts': self.articles,
                'sets': {'일반직': {'regs': regs}}}
        for target, name, value in [(reg.regstore, 'data', data), (reg.llm, 'available', True),
                                    (reg.question_classifier, 'classify', {'label': '사내 규정'})]:
            mock = patch.object(target, name, return_value=value)
            setattr(self, name, mock.start())
            self.addCleanup(mock.stop)
        search = patch.object(reg.regstore, 'search', return_value=[{'id': 'work-2'}])
        self.search = search.start()
        self.addCleanup(search.stop)
        self.history = [{'q': '인재개발규정 제7조 알려줘',
                         'a': {'kind': 'regulation', 'level': 'ok', 'summary': '학습시간을 인정해요.',
                               'basis': ['edu-7'], 'apply': '이전 적용 안내', 'more': ['이전 추가 안내'],
                               'missing': ['이전 미등록 기준']}}]

    def ask(self, question, history=None, status='found', source_ids=None, summary='교육 신청은 교육포털에서 해요.'):
        inp = {'question': question, 'me': self.ctx.me, 'context': {},
               'history': self.history if history is None else history}
        response = {'status': status, 'summary': summary,
                    'sourceIds': source_ids if source_ids is not None else
                                 ['S001'] if status in ('found', 'partial') else []}
        with patch.object(rt, 'llm_json', return_value=response) as model:
            result = reg._api(self.ctx, inp)
        return result, model, inp

    def assert_summary_history(self, model):
        self.assertEqual(model.call_args.kwargs['history'], [
            {'role': 'user', 'content': self.history[0]['q']},
            {'role': 'assistant', 'content': self.history[0]['a']['summary']},
        ])

    def test_article_follow_up_prioritizes_requested_article_and_keeps_summary(self):
        for question in ('그 규정 제9조 내용을 알려줘', '그럼 제9조는?', '제9조는요?',
                         '앞에서 설명한 규정의 제9조 내용을 자세히 알려 주세요'):
            with self.subTest(question=question):
                first, _, _ = self.ask('인재개발규정 제7조 알려줘', history=[], summary='학습시간을 인정해요.')
                self.history[0]['a'] = first
                result, model, _ = self.ask(question)
                self.assertEqual(result['basis'], ['edu-9'])
                self.assertEqual(result['retrieved'], ['edu-9', 'edu-7', 'work-2'])
                payload = model.call_args.args[2]
                self.assertEqual(payload['requested']['where'], '제9조')
                self.assertEqual(payload['sources'][0]['regulation'], '인재개발규정')
                self.assertEqual(payload['sources'][0]['no'], '제9조')
                self.assert_summary_history(model)

    def test_reference_fallback_does_not_claim_classifier_used_history(self):
        _, model, inp = self.ask('그 규정 제9조 내용을 알려줘')
        self.assertEqual(self.classify.call_args.args[0], '그 규정 제9조 내용을 알려줘')
        self.assertFalse(inp['_classification']['usedHistory'])
        self.assert_summary_history(model)

    def test_explicit_other_regulation_does_not_inherit_previous_sources(self):
        result, model, _ = self.ask('취업규칙 제9조 내용을 자세히 알려 주세요')
        self.assertEqual(result['basis'], ['work-9'])
        self.assertNotIn('edu-7', result['retrieved'])
        self.assertEqual(model.call_args.kwargs['history'], [])

    def test_explicit_same_regulation_is_independent(self):
        result, model, _ = self.ask('인재개발규정 제9조 내용을 알려줘')
        self.assertEqual(result['basis'], ['edu-9'])
        self.assertNotIn('edu-7', result['retrieved'])
        self.assertEqual(model.call_args.kwargs['history'], [])

    def test_unrelated_question_does_not_inherit_regulation(self):
        result, model, _ = self.ask('취업규칙의 적용 범위를 자세히 알려 주세요')
        self.assertEqual(result['retrieved'], ['work-2'])
        self.assertNotIn('requested', model.call_args.args[2])
        self.assertEqual(model.call_args.kwargs['history'], [])

    def test_no_previous_regulation_does_not_guess_article(self):
        for history in ([], [{'q': '다른 질문', 'a': {'summary': '앞 답변', 'basis': []}}],
                        [{'q': '다른 질문', 'a': {'summary': '앞 답변', 'basis': ['deleted-id']}}]):
            with self.subTest(history=history):
                _, model, _ = self.ask('그 규정 제9조 내용을 알려줘', history=history)
                self.assertNotIn('requested', model.call_args.args[2])
                self.assertEqual(model.call_args.kwargs['history'], [])

    def test_unregistered_article_keeps_note_and_summary_history(self):
        result, model, _ = self.ask('그 규정 제99조 내용을 알려줘', status='not_found')
        self.assertEqual(result['evidenceStatus'], 'not_found')
        self.assertIn('인재개발규정', result['summary'])
        self.assertIn('제99조', result['summary'])
        self.assertEqual(result['basis'], [])
        self.assertEqual(model.call_args.args[2]['sources'], [])
        self.assert_summary_history(model)

    def test_summary_history_excludes_old_shape_and_real_ids_without_mutation(self):
        original = copy.deepcopy(self.history)
        _, model, _ = self.ask('그럼 제9조는?')
        self.assert_summary_history(model)
        self.assertEqual(self.history, original)

    def test_history_without_summary_uses_empty_text(self):
        self.history[0]['a'].pop('summary')
        messages = reg._hist_msgs(self.history)
        self.assertEqual(messages[-1], {'role': 'assistant', 'content': ''})

    def test_old_real_citation_id_is_still_rejected(self):
        with self.assertRaisesRegex(LlmError, '출처'):
            self.ask('그럼 제9조는?', source_ids=['edu-7'])


if __name__ == '__main__':
    unittest.main()
