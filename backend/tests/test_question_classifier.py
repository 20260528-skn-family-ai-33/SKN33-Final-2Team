"""외부 DB·LLM·모델 다운로드 없이 분류 연결과 실패 처리를 검증한다."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app import question_classifier as classifier
from app.agents import regulation as reg
from app.agents import runtime as rt
from app.errors import cause
from app.llm import LlmError


class ClassifierFilesTest(unittest.TestCase):
    def setUp(self):
        self.cache = patch.object(classifier, '_loaded', None)
        self.cache.start()
        self.addCleanup(self.cache.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.model_dir = patch.object(classifier, 'MODEL_DIR', self.directory)
        self.model_dir.start()
        self.addCleanup(self.model_dir.stop)

    def write_manifest(self, **changes):
        files = ('klue_roberta_full_model.pt', 'tokenizer.json', 'tokenizer_config.json', 'config.json')
        for name in files:
            (self.directory / name).write_bytes(b'test fixture')
        data = {'labels': list(classifier.LABELS), 'max_length': 128,
                'sha256': {name: hashlib.sha256(b'test fixture').hexdigest() for name in files}}
        data.update(changes)
        (self.directory / 'classifier-manifest.json').write_text(json.dumps(data), encoding='utf-8')

    def test_empty_question_does_not_load(self):
        with patch.object(classifier, '_load') as load:
            with self.assertRaisesRegex(LlmError, '비어'):
                classifier.classify('  ')
            load.assert_not_called()

    def test_missing_model_is_explicit_error(self):
        with self.assertRaisesRegex(LlmError, '준비 실패'):
            classifier.classify('질문')

    def test_changed_checkpoint_rejected_before_deserialization(self):
        self.write_manifest()
        (self.directory / 'klue_roberta_full_model.pt').write_bytes(b'changed')
        with self.assertRaisesRegex(LlmError, '준비 실패') as error:
            classifier.classify('질문')
        self.assertIn('해시', str(error.exception.__cause__))

    def test_changed_tokenizer_rejected(self):
        self.write_manifest()
        (self.directory / 'tokenizer.json').write_bytes(b'changed')
        with self.assertRaisesRegex(LlmError, '준비 실패'):
            classifier.classify('질문')

    def test_wrong_label_order_rejected(self):
        self.write_manifest(labels=list(reversed(classifier.LABELS)))
        with self.assertRaisesRegex(LlmError, '준비 실패'):
            classifier.classify('질문')

    def test_wrong_training_length_rejected(self):
        self.write_manifest(max_length=512)
        with self.assertRaisesRegex(LlmError, '준비 실패'):
            classifier.classify('질문')

    def test_classifier_error_has_specific_action(self):
        info = cause('질문 분류 모델 준비 실패', 'ollama')
        self.assertEqual(info['code'], 'AI_CLASSIFIER')
        self.assertIn('classifier-manifest.json', info['hint'])
        self.assertFalse(info['retryable'])


class ClassifierRoutingTest(unittest.TestCase):
    def setUp(self):
        self.ctx = rt.Ctx(employee_id=1, me={'empGroup': '일반직'})
        self.inp = {'question': '교육비 지원 기준은?', 'me': self.ctx.me, 'history': [], 'context': {}}
        self.predict = patch.object(classifier, 'classify', return_value={'label': '사내 규정', 'confidence': 0.9})
        self.classify = self.predict.start()
        self.addCleanup(self.predict.stop)
        self.available = patch('app.llm.available', return_value=True)
        self.available.start()
        self.addCleanup(self.available.stop)
        self.knowledge = patch.object(reg.knowledge, 'search_company', return_value=[])
        self.company_search = self.knowledge.start()
        self.addCleanup(self.knowledge.stop)

    def test_out_of_scope_never_searches_or_calls_llm(self):
        self.classify.return_value = {'label': '범위 밖'}
        with patch.object(reg.regstore, 'search') as search, patch.object(rt, 'llm_json') as llm:
            result = reg._api(self.ctx, self.inp)
        self.assertEqual(result['kind'], 'out')
        search.assert_not_called()
        llm.assert_not_called()

    def test_load_failure_is_not_replaced_by_llm(self):
        self.classify.side_effect = LlmError('질문 분류 모델 준비 실패')
        with patch.object(rt, 'llm_json') as llm:
            with self.assertRaises(LlmError):
                reg._api(self.ctx, self.inp)
        llm.assert_not_called()

    def run_route(self, label, response=None, responses=None):
        self.classify.return_value = {'label': label}
        with patch.object(reg.regstore, 'search', return_value=[]) as search, \
             patch.object(reg.regstore, 'explicit_ref', return_value=None), \
             patch.object(rt, 'llm_json', return_value=response, side_effect=responses) as llm:
            result = reg._api(self.ctx, self.inp)
        return result, search, llm

    def test_regulation_keeps_search_and_no_evidence_guard(self):
        result, search, _ = self.run_route('사내 규정', {'kind': 'regulation', 'level': 'ok', 'summary': '근거 없는 답', 'basis': ['unknown']})
        self.assertEqual(search.call_count, 1)
        self.assertEqual(result['kind'], 'regulation')
        self.assertEqual(result['level'], 'none')
        self.assertEqual(result['basis'], [])

    def test_life_guidance_skips_embeddings_and_forces_menu_source(self):
        menu_id = reg.D['intranet'][0]['id']
        result, search, llm = self.run_route('사내 생활안내', {'kind': 'general', 'source': 'work', 'intranet': [menu_id, 'unknown']})
        search.assert_not_called()
        self.assertEqual(result['source'], 'intranet')
        self.assertEqual(result['intranet'], [menu_id])
        self.assertEqual(llm.call_args.args[2]['classification']['label'], '사내 생활안내')

    def test_company_without_hits_does_not_call_llm(self):
        result, search, llm = self.run_route('수자원공사 정보', {})
        self.assertEqual(result['kind'], 'general')
        self.assertEqual(result['source'], 'work')
        self.assertEqual(result['knowledgeSources'], [])
        self.company_search.assert_called_once()
        search.assert_not_called()
        llm.assert_not_called()

    def company_hit(self, **changes):
        hit = {'chunk_id': 'company-1', 'document_id': 'company', 'document_title': '회사 소개',
               'category': '수자원공사 정보', 'is_virtual': False,
               'chunk_text': '수돗물 공급과 수자원 관리 업무를 수행한다.',
               'chunk_text_sha256': 'a' * 64,
               'metadata': {'location': 'PDF 3쪽', 'as_of': '2025 보고서 기준', 'source_url': 'https://example.invalid/source'}}
        hit.update(changes)
        return hit

    def test_company_passes_database_text_and_returns_valid_source(self):
        self.company_search.return_value = [self.company_hit()]
        result, search, llm = self.run_route('수자원공사 정보', {
            'answerable': True, 'summary': '수돗물 공급과 수자원 관리를 수행해요.', 'sourceIds': ['company-1']})
        search.assert_not_called()
        self.assertIn('수돗물 공급', llm.call_args.args[2]['sources'][0]['text'])
        self.assertEqual(llm.call_args.kwargs['role'], 'regulation')
        self.assertEqual(result['knowledgeSources'][0]['chunkId'], 'company-1')
        self.assertFalse(result['knowledgeSources'][0]['isVirtual'])
        self.assertIn('출처: 회사 소개', result['summary'])

    def test_company_rejects_unknown_citation(self):
        self.company_search.return_value = [self.company_hit()]
        with self.assertRaisesRegex(LlmError, '출처'):
            self.run_route('수자원공사 정보', {'answerable': True, 'summary': '답변', 'sourceIds': ['unknown']})

    def test_company_rejects_virtual_workplace_material(self):
        self.company_search.return_value = [self.company_hit(is_virtual=True)]
        with self.assertRaisesRegex(LlmError, '범주'):
            self.run_route('수자원공사 정보', {})

    def test_company_rejects_unsupported_number(self):
        self.company_search.return_value = [self.company_hit()]
        with self.assertRaisesRegex(LlmError, '숫자'):
            self.run_route('수자원공사 정보', {'answerable': True, 'summary': '직원은 999명입니다.', 'sourceIds': ['company-1']})

    def test_company_can_decline_when_retrieved_text_does_not_answer(self):
        self.company_search.return_value = [self.company_hit()]
        result, _, _ = self.run_route('수자원공사 정보', {'answerable': False, 'summary': '', 'sourceIds': []})
        self.assertEqual(result['knowledgeSources'], [])
        self.assertIn('충분한 근거', result['summary'])

    def confirmation(self):
        return {'kind': 'clarify', 'question': '부산의 일반 날씨인가요, 업무 중 기상 대응 규정인가요?',
                'options': ['부산의 일반 날씨를 알려 주세요.', '업무 중 기상 대응 규정을 알려 주세요.']}

    def after_confirmation(self, reply):
        self.inp.update(question=reply, history=[{'q': '부산 날씨 알려줘', 'a': self.confirmation()}])

    def test_conflicting_interpretations_ask_without_exposing_answer(self):
        for label, kind in [('사내 규정', 'general'), ('사내 규정', 'out_of_scope'),
                            ('사내 생활안내', 'regulation'), ('사내 생활안내', 'out')]:
            with self.subTest(label=label, kind=kind):
                result, _, model = self.run_route(label, responses=[
                    {'kind': kind, 'summary': '검증되지 않은 사실 답변', 'basis': ['unknown']}, self.confirmation()])
                self.assertEqual(result['kind'], 'clarify')
                self.assertIn('일반 날씨', result['question'])
                self.assertEqual(result['summary'], '')
                self.assertEqual(result['basis'], [])
                self.assertEqual(result['retrieved'], [])
                self.assertEqual(model.call_count, 2)
                self.assertEqual(model.call_args.kwargs['role'], 'regulation')
                self.assertNotIn('검증되지 않은 사실 답변', str(model.call_args))

    def test_unknown_or_malformed_response_is_not_semantic_conflict(self):
        for response in ({}, [], None, {'kind': 'unknown'}, {'kind': ['regulation']}):
            with self.subTest(response=response):
                with self.assertRaisesRegex(LlmError, '답변 유형'):
                    self.run_route('사내 규정', response)

    def test_bad_json_is_not_converted_to_clarification(self):
        with patch.object(rt.llm, 'chat', return_value={'content': 'invalid json'}), \
             patch.object(reg.regstore, 'search', return_value=[]), \
             patch.object(reg.regstore, 'explicit_ref', return_value=None):
            with self.assertRaisesRegex(LlmError, 'JSON'):
                reg._api(self.ctx, self.inp)

    def test_invalid_confirmation_remains_system_error(self):
        for response in ({'kind': 'out'}, {'kind': 'clarify', 'question': [], 'options': []},
                         {'kind': 'clarify', 'question': '어떤 뜻인가요?', 'options': '질문'},
                         {'kind': 'clarify', 'question': '어떤 뜻인가요?', 'options': [{}]}):
            with self.subTest(response=response):
                with self.assertRaisesRegex(LlmError, '의도 확인'):
                    self.run_route('사내 규정', responses=[{'kind': 'out'}, response])

    def test_direct_option_reclassifies_only_selected_question(self):
        selected = self.confirmation()['options'][1]
        self.after_confirmation(selected)
        result, search, model = self.run_route('사내 규정', {'kind': 'regulation', 'level': 'none'})
        self.classify.assert_called_once_with(selected)
        self.assertTrue(self.inp['_classification']['usedHistory'])
        search.assert_called_once_with(selected, 4, '일반직', self.ctx.mode)
        self.assertEqual(model.call_count, 1)
        self.assertEqual(model.call_args.args[2]['confirmedIntent']['reply'], selected)
        self.assertEqual(result['kind'], 'regulation')

    def test_outside_option_does_not_search_or_generate(self):
        selected = self.confirmation()['options'][0]
        self.after_confirmation(selected)
        result, search, model = self.run_route('범위 밖')
        self.classify.assert_called_once_with(selected)
        self.assertEqual(result['kind'], 'out')
        search.assert_not_called()
        self.company_search.assert_not_called()
        model.assert_not_called()

    def test_numbered_option_resolves_to_full_question(self):
        for reply in ('2', '2번', '2번째', '2번요'):
            with self.subTest(reply=reply):
                self.classify.reset_mock()
                self.after_confirmation(reply)
                result, _, _ = self.run_route('사내 규정', {'kind': 'regulation', 'level': 'none'})
                self.classify.assert_called_once_with(self.confirmation()['options'][1])
                self.assertEqual(result['kind'], 'regulation')

    def test_yes_no_or_invalid_choice_does_not_choose_an_intent(self):
        for reply in ('네', '아니요', '3번'):
            with self.subTest(reply=reply):
                self.after_confirmation(reply)
                result, search, model = self.run_route('사내 규정')
                self.assertEqual(result['kind'], 'clarify')
                self.assertEqual(result['options'], self.confirmation()['options'])
                self.classify.assert_not_called()
                search.assert_not_called()
                model.assert_not_called()

    def test_free_reply_uses_confirmation_and_reclassifies_resolved_intent(self):
        self.after_confirmation('규정 쪽이요')
        resolved = '업무 중 기상 대응 규정을 알려 주세요.'
        result, search, model = self.run_route('사내 규정', responses=[
            {'kind': 'resolved', 'resolvedQuestion': resolved}, {'kind': 'regulation', 'level': 'none'}])
        resolution = model.call_args_list[0]
        self.assertEqual(resolution.args[2]['reply'], '규정 쪽이요')
        self.assertEqual(resolution.args[2]['confirmationQuestion'], self.confirmation()['question'])
        self.assertEqual(resolution.args[2]['originalQuestion'], '부산 날씨 알려줘')
        self.classify.assert_called_once_with(resolved)
        search.assert_called_once_with(resolved, 4, '일반직', self.ctx.mode)
        self.assertEqual(result['kind'], 'regulation')

    def test_unresolved_free_reply_still_asks_without_classifier_or_search(self):
        self.after_confirmation('그건 아니고요')
        result, search, model = self.run_route('사내 규정', self.confirmation())
        self.assertEqual(result['kind'], 'clarify')
        self.classify.assert_not_called()
        search.assert_not_called()
        self.assertEqual(model.call_count, 1)

    def test_new_topic_after_confirmation_is_classified_by_itself(self):
        self.after_confirmation('구내식당 식단은 어디서 확인하나요?')
        menu_id = reg.D['intranet'][0]['id']
        result, search, model = self.run_route('사내 생활안내', responses=[
            {'kind': 'resolved', 'resolvedQuestion': self.inp['question']}, {'kind': 'general', 'intranet': [menu_id]}])
        self.classify.assert_called_once_with(self.inp['question'])
        search.assert_not_called()
        self.assertEqual(result['source'], 'intranet')
        self.assertEqual(model.call_count, 2)

    def test_malformed_resolved_intent_is_not_classified(self):
        self.after_confirmation('규정 쪽이요')
        for response in ({}, {'kind': 'resolved', 'resolvedQuestion': ''}, {'kind': 'resolved', 'resolvedQuestion': []}):
            with self.subTest(response=response):
                with self.assertRaisesRegex(LlmError, '확인된 질문'):
                    self.run_route('사내 규정', response)
                self.classify.assert_not_called()

    def test_confirmation_cannot_skip_classifier_failure(self):
        self.after_confirmation('2번')
        self.classify.side_effect = LlmError('질문 분류 모델 추론 실패')
        with self.assertRaisesRegex(LlmError, '분류 모델'):
            self.run_route('사내 규정')

    def test_confirmation_filters_unsupported_numbers_and_explanations(self):
        result, _, _ = self.run_route('사내 규정', {
            'kind': 'clarify', 'question': '휴가가 999일이라는 뜻인가요?',
            'options': ['휴가가 999일인가요?', '휴가 신청은 어디서 하나요? (999일 사용 가능)', '교육 신청은 어디서 하나요? 답은 999일이에요.']})
        self.assertNotIn('999', json.dumps(result, ensure_ascii=False))
        self.assertEqual(len(result['options']), 2)

    def test_confirmed_intent_keeps_regulation_number_guard(self):
        self.after_confirmation('2번')
        article = {'id': 'r1', 'title': '기상 대응', 'text': '업무 중 기상 대응 기준을 정한다.',
                   'reg': 'reg1', 'no': '제1조', 'chapter': ''}
        with patch.object(reg.regstore, 'article', return_value=article), \
             patch.object(reg.regstore, 'reg_public', return_value={'name': '기상 규정'}), \
             patch.object(reg.regstore, 'search', return_value=[{'id': 'r1'}]), \
             patch.object(reg.regstore, 'explicit_ref', return_value=None), \
             patch.object(rt, 'llm_json', return_value={'kind': 'regulation', 'level': 'ok', 'summary': '999일 휴가예요.', 'basis': ['r1']}):
            result = reg._api(self.ctx, self.inp)
        self.assertEqual(result['level'], 'unclear')
        self.assertTrue(result['dropped'])

    def test_ambiguous_question_can_still_clarify(self):
        result, _, _ = self.run_route('사내 규정', {'kind': 'clarify', 'question': '어떤 기준인가요?', 'options': ['입사일인가요?', '월별 계산 시작일인가요?']})
        self.assertEqual(result['kind'], 'clarify')
        self.assertEqual(len(result['options']), 2)

    def test_follow_up_uses_previous_question(self):
        self.classify.return_value = {'label': '범위 밖'}
        self.inp.update(question='그럼 신청은 언제까지?', history=[{'q': '교육비 지원 기준은?', 'a': {'kind': 'regulation', 'basis': []}}])
        reg._api(self.ctx, self.inp)
        self.assertIn('교육비 지원', self.classify.call_args.args[0])
        self.assertTrue(self.inp['_classification']['usedHistory'])

    def test_explicit_new_out_question_does_not_inherit_history(self):
        self.classify.return_value = {'label': '범위 밖'}
        self.inp.update(question='오늘 날씨 어때?', history=[{'q': '교육비 지원 기준은?', 'a': {'kind': 'regulation'}}])
        reg._api(self.ctx, self.inp)
        self.classify.assert_called_once_with('오늘 날씨 어때?')

    def test_demo_mode_does_not_load_classifier(self):
        self.ctx.demo = True
        with patch.object(reg, '_mock', return_value=reg.ans(kind='out')), patch.object(rt, '_log'), patch.object(rt.time, 'sleep'):
            self.assertEqual(reg.answer(self.ctx, '질문', [], {})['kind'], 'out')
        self.classify.assert_not_called()
        self.assertNotIn('classification', self.ctx.meta)

    def test_real_answer_exposes_classifier_metadata(self):
        self.classify.return_value = {'label': '범위 밖', 'confidence': 0.99}
        with patch.object(rt, '_log'):
            result = reg.answer(self.ctx, '오늘 날씨 어때?', [], {})
        self.assertEqual(result['kind'], 'out')
        self.assertEqual(self.ctx.meta['classification']['label'], '범위 밖')


if __name__ == '__main__':
    unittest.main()
