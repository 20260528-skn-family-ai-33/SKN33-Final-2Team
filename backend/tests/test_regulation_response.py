"""규정 5-1단계의 상태별 고정 안내·인용 보존·검증 실패를 검사한다."""
from __future__ import annotations

import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app.agents import regulation as reg, runtime as rt
from app.llm import LlmError


class RegulationResponseTest(unittest.TestCase):
    def setUp(self):
        self.ctx = rt.Ctx(1)
        self.inp = {'question': '성과급 지급 기준은?', 'context': {}}
        self.article = {'id': 'reg-1', 'title': '성과상여금', 'text': '성과상여금은 매년 지급한다.'}
        self.article_lookup = self.enterContext(patch.object(
            reg.regstore, 'article', side_effect=lambda value: self.article if value == 'reg-1' else None))
        self.model = self.enterContext(patch.object(rt, 'llm_json', side_effect=AssertionError('5-1단계 추가 모델 호출 금지')))

    def format(self, status, summary='성과상여금은 매년 지급해요.', source_ids=None, retrieved=None):
        result = {'status': status, 'summary': summary,
                  'sourceIds': ['reg-1'] if source_ids is None else source_ids}
        return reg.format_regulation_response(self.ctx, self.inp, ['reg-1'] if retrieved is None else retrieved, result)

    def test_refused_preserves_reason_without_adding_sources(self):
        for ids in ([], ['reg-1']):
            with self.subTest(ids=ids):
                reason = '타인의 비공개 인사정보 공개 요청이라 제공할 수 없어요.'
                result = self.format('refused', summary=reason, source_ids=[], retrieved=ids)
                self.assertEqual(result['evidenceStatus'], 'refused')
                self.assertEqual(result['summary'], reason)
                self.assertEqual(result['basis'], [])
                self.assertEqual(result['retrieved'], [])
        self.article_lookup.assert_not_called()
        self.model.assert_not_called()

    def test_not_found_preserves_reason_and_explicit_missing_article_note(self):
        reason = '이번 검색에서 성과급 지급 기준을 확인하지 못했어요.'
        result = self.format('not_found', summary=reason, source_ids=[], retrieved=[])
        self.assertEqual(result['evidenceStatus'], 'not_found')
        self.assertEqual(result['summary'], reason)
        self.assertEqual(result['basis'], [])
        self.inp['_ref_empty_note'] = '요청한 규정의 제99조가 등록되지 않았어요.'
        result = self.format('not_found', summary=reason, source_ids=[], retrieved=[])
        self.assertIn(self.inp['_ref_empty_note'], result['summary'])
        self.assertIn(reason, result['summary'])
        self.article_lookup.assert_not_called()

    def test_not_found_with_retrieved_sources_is_a_contract_error(self):
        with self.assertRaisesRegex(LlmError, '검색 자료가 있는'):
            self.format('not_found', source_ids=[])

    def test_partial_keeps_cited_scope_even_when_hr_question_term_is_absent(self):
        self.article.update(title='직원 평가', text='직원 평가는 정기적으로 실시한다.')
        self.inp['question'] = '승진 기준은 어떻게 되나요?'
        summary = '검색된 자료는 직원 평가를 안내하고 있어요. 승진 기준은 해당 자료에서 확인되지 않아요.'
        self.assertFalse(reg.hr_stated(self.inp['question'], ['reg-1']))
        result = self.format('partial', summary)
        self.assertEqual((result['evidenceStatus'], result['level']), ('partial', 'unclear'))
        self.assertEqual(result['summary'], summary)
        self.assertEqual(result['basis'], ['reg-1'])
        self.assertEqual(result['retrieved'], ['reg-1'])
        self.model.assert_not_called()

    def test_found_preserves_summary_and_citation_despite_different_hr_wording(self):
        self.assertFalse(reg.hr_stated(self.inp['question'], ['reg-1']))
        generated = {'status': 'found', 'summary': '성과상여금은 매년 지급해요.', 'sourceIds': ['reg-1']}
        original = copy.deepcopy(generated)
        result = reg.format_regulation_response(self.ctx, self.inp, ['reg-1'], generated)
        self.assertEqual((result['evidenceStatus'], result['level']), ('found', 'ok'))
        self.assertEqual(result['summary'], generated['summary'])
        self.assertEqual(result['basis'], generated['sourceIds'])
        self.assertEqual(generated, original)
        self.model.assert_not_called()

    def test_cited_answer_requires_nonempty_summary_and_current_existing_sources(self):
        for status in ('partial', 'found'):
            for summary, source_ids, retrieved in (
                ('', ['reg-1'], ['reg-1']), ('   ', ['reg-1'], ['reg-1']),
                (None, ['reg-1'], ['reg-1']), ('요약', [], ['reg-1']),
                ('요약', 'reg-1', ['reg-1']), ('요약', [1], ['reg-1']),
                ('요약', ['reg-1'], ['other']), ('요약', ['deleted'], ['deleted']),
            ):
                with self.subTest(status=status, summary=summary, ids=source_ids, retrieved=retrieved):
                    with self.assertRaisesRegex(LlmError, '형식 오류'):
                        self.format(status, summary, source_ids, retrieved)

    def test_invalid_status_does_not_fall_through_to_found(self):
        for result in (None, [], {}, {'status': 'unknown'}):
            with self.subTest(result=result), self.assertRaisesRegex(LlmError, '근거 확인 상태'):
                reg.format_regulation_response(self.ctx, self.inp, [], result)

    def test_unsupported_numbers_remain_errors_for_partial_and_found(self):
        self.article.update(text='지원 한도는 10만원이다.')
        for status in ('partial', 'found'):
            with self.subTest(status=status), self.assertRaisesRegex(LlmError, '숫자'):
                self.format(status, '지원 한도는 20만원이에요.')

    def test_user_context_numbers_keep_existing_exception(self):
        self.inp['context'] = {'grade': 5}
        for status in ('partial', 'found'):
            with self.subTest(status=status):
                result = self.format(status, '5급 직원의 지급 기준은 해당 규정을 확인해 주세요.')
                self.assertEqual(result['evidenceStatus'], status)


if __name__ == '__main__':
    unittest.main()
