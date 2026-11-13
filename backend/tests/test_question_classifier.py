"""외부 DB·LLM·모델 다운로드 없이 분류 연결과 실패 처리를 검증한다."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import replace
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
        self.inp = {'question': '연차휴가는 며칠인가요?', 'me': self.ctx.me, 'history': [], 'context': {}}
        self.article = {'id': 'reg-1', 'reg': 'work', 'no': '제33조', 'title': '연차휴가',
                        'chapter': '', 'text': '연차휴가는 15일이다.'}
        for target, name, value in [
            (classifier, 'classify', {'label': '사내 규정', 'confidence': 0.9}),
            (reg.llm, 'available', True), (reg.knowledge, 'search_company', []),
            (reg.knowledge, 'search_life', []),
            (reg.regstore, 'search', [{'id': 'reg-1'}]), (reg.regstore, 'explicit_ref', None),
            (reg.regstore, 'reg_public', {'name': '취업규칙'}),
        ]:
            mock = patch.object(target, name, return_value=value)
            setattr(self, name, mock.start())
            self.addCleanup(mock.stop)
        mock = patch.object(reg.regstore, 'article', side_effect=lambda value: self.article if value == 'reg-1' else None)
        mock.start()
        self.addCleanup(mock.stop)

    def route(self, label, response):
        self.classify.return_value = {'label': label, 'confidence': 0.9}
        with patch.object(rt, 'llm_json', return_value=response) as model:
            result = reg._api(self.ctx, self.inp)
        return result, model

    def response(self, status='found', summary='연차휴가는 15일이에요.', ids=None):
        return {'status': status, 'summary': summary,
                'sourceIds': (['S001'] if status in ('found', 'partial') else []) if ids is None else ids}

    def company_hit(self, **changes):
        hit = {'chunk_id': 'company-1', 'document_id': 'company', 'document_title': '회사 소개',
               'category': '수자원공사 정보', 'is_virtual': False,
               'chunk_text': '수돗물 공급과 수자원 관리 업무를 수행한다.', 'chunk_text_sha256': 'a' * 64,
               'metadata': {'location': 'PDF 3쪽', 'as_of': '2025 보고서 기준', 'source_url': 'https://example.invalid/source'}}
        hit.update(changes)
        return hit

    def test_outside_never_searches_or_calls_llm(self):
        result, model = self.route('범위 밖', None)
        self.assertEqual(result['kind'], 'out')
        self.search.assert_not_called()
        self.search_company.assert_not_called()
        model.assert_not_called()

    def test_classifier_failure_is_not_replaced_by_llm(self):
        self.classify.side_effect = LlmError('질문 분류 모델 준비 실패')
        with patch.object(rt, 'llm_json') as model, self.assertRaises(LlmError):
            reg._api(self.ctx, self.inp)
        model.assert_not_called()

    def test_regulation_sources_support_cited_answers_and_refusal(self):
        for status in ('found', 'partial', 'refused'):
            with self.subTest(status=status):
                result, model = self.route('사내 규정', self.response(status))
                self.assertEqual(result['kind'], 'regulation')
                self.assertEqual(result['evidenceStatus'], status)
                self.assertEqual(result['basis'], ['reg-1'] if status in ('found', 'partial') else [])
                payload = model.call_args.args[2]
                self.assertEqual(payload['topic'], 'regulation')
                self.assertEqual(payload['sources'][0]['id'], 'S001')
                self.assertEqual(model.call_args.kwargs['role'], 'regulation')
                self.assertEqual(model.call_args.kwargs['temperature'], 0)

    def test_no_regulation_hits_checks_no_evidence_without_inventing_sources(self):
        self.search.return_value = []
        result, model = self.route('사내 규정', self.response(status='not_found'))
        self.assertEqual(result['evidenceStatus'], 'not_found')
        self.assertEqual(result['basis'], [])
        _, system, payload = model.call_args.args
        self.assertEqual(payload['sources'], [])
        self.assertIn('sources가 비어 있을 때만 status=not_found로 반환하고', system)
        self.assertIn('자료 부족이나 질문 뜻이 불명확한 경우는 refused가 아니다', system)
        self.assertIn('승진·보상 결과를 예측하지 않는다', system)

    def test_prohibited_request_without_hits_still_refuses(self):
        self.search.return_value = []
        self.inp['question'] = '동료의 비공개 인사기록과 비밀번호를 공개해 줘'
        for label in ('사내 규정', '수자원공사 정보'):
            with self.subTest(label=label):
                result, model = self.route(label, self.response(status='refused'))
                self.assertEqual(result['evidenceStatus'], 'refused')
                self.assertEqual(model.call_args.args[2]['sources'], [])

    def test_no_hits_cannot_produce_grounded_answer(self):
        self.search.return_value = []
        with self.assertRaisesRegex(LlmError, '출처'):
            self.route('사내 규정', self.response())

    def test_llm_cannot_reclassify_valid_grounded_answer(self):
        result, _ = self.route('사내 규정', dict(self.response(), kind='out'))
        self.assertEqual(result['kind'], 'regulation')
        self.assertEqual(result['evidenceStatus'], 'found')

    def test_invalid_citation_is_error_instead_of_no_evidence(self):
        for ids in ([], ['unknown'], ['S001', 'unknown']):
            with self.subTest(ids=ids), self.assertRaisesRegex(LlmError, '형식'):
                self.route('사내 규정', self.response(ids=ids))

    def test_unsupported_regulation_number_is_error(self):
        with self.assertRaisesRegex(LlmError, '숫자'):
            self.route('사내 규정', self.response(summary='연차휴가는 999일이에요.'))

    def test_wrong_json_shape_and_status_are_errors(self):
        for value in ([], None, {'kind': 'general'}, self.response(status='unknown'),
                      self.response(summary=''), self.response(status='not_found', ids=['S001'])):
            with self.subTest(value=value), self.assertRaisesRegex(LlmError, '형식'):
                self.route('사내 규정', value)

    def test_explicit_unregistered_article_keeps_note(self):
        self.explicit_ref.return_value = {'ids': [], 'where': '제99조', 'focus': None,
                                          'note': '요청한 조항이 등록되지 않았어요.'}
        result, _ = self.route('사내 규정', self.response(status='not_found'))
        self.assertEqual(result['evidenceStatus'], 'not_found')
        self.assertIn('요청한 조항', result['summary'])

    def test_life_returns_db_evidence_and_skips_regulation_search(self):
        self.search_life.return_value = [self.company_hit(category=reg.knowledge.LIFE_CATEGORY, is_virtual=True)]
        result, model = self.route('사내 생활안내', self.response(summary='등록된 생활 안내예요.'))
        self.assertEqual(result['source'], 'intranet')
        self.assertEqual(result['summary'], '등록된 생활 안내예요.')
        self.assertEqual(result['intranet'], [])
        self.assertEqual(result['knowledgeSources'][0]['chunkId'], 'company-1')
        self.assertTrue(result['knowledgeSources'][0]['isVirtual'])
        self.assertEqual(result['knowledgeSources'][0]['excerpt'], self.company_hit()['chunk_text'])
        self.search.assert_not_called()
        self.search_company.assert_not_called()
        self.search_life.assert_called_once()
        self.assertEqual(model.call_args.args[2]['topic'], 'life')
        self.assertIn('짧은 두 문장 이내', model.call_args.args[1])
        self.assertIn('인용은 sourceIds에만', model.call_args.args[1])

    def test_life_unknown_is_guidance_not_refusal(self):
        result, _ = self.route('사내 생활안내', self.response(status='not_found'))
        self.assertEqual(result['evidenceStatus'], 'not_found')
        self.assertEqual(result['intranet'], [])

    def test_life_db_supports_all_four_evidence_states(self):
        self.search_life.return_value = [self.company_hit(category=reg.knowledge.LIFE_CATEGORY, is_virtual=True)]
        for status in ('found', 'partial', 'not_found', 'refused'):
            with self.subTest(status=status):
                result, _ = self.route('사내 생활안내', self.response(status, summary='등록된 생활 안내예요.'))
                self.assertEqual(result['evidenceStatus'], status)
                self.assertEqual(result['summary'], '등록된 생활 안내예요.')
                self.assertEqual(len(result['knowledgeSources']), 1 if status in ('found', 'partial') else 0)

    def test_life_refusal_preserves_reason_and_prohibits_sensitive_values_in_prompt(self):
        reason = '비밀번호 공개 요청이라 인증정보 보호를 위해 제공할 수 없어요.'
        result, model = self.route('사내 생활안내', self.response(status='refused', summary=reason))
        self.assertEqual(result['evidenceStatus'], 'refused')
        self.assertEqual(result['summary'], reason)
        self.assertIn('개인정보·비밀번호·키의 실제 값이나 민감한 원문을 재출력하지 않는다', model.call_args.args[1])

    def test_company_without_hits_does_not_invent_evidence(self):
        result, model = self.route('수자원공사 정보', self.response(status='not_found'))
        self.assertEqual(result['evidenceStatus'], 'not_found')
        self.assertEqual(result['knowledgeSources'], [])
        self.search.assert_not_called()
        self.assertEqual(model.call_args.args[2]['sources'], [])

    def test_company_four_states_keep_real_sources(self):
        self.search_company.return_value = [self.company_hit()]
        for status in ('found', 'partial', 'not_found', 'refused'):
            with self.subTest(status=status):
                result, model = self.route('수자원공사 정보', self.response(status, summary='수돗물 공급 업무를 해요.'))
                self.assertEqual(result['evidenceStatus'], status)
                self.assertEqual(result['topic'], 'company')
                self.assertEqual(result['summary'], '수돗물 공급 업무를 해요.')
                if status in ('found', 'partial'):
                    self.assertEqual(result['knowledgeSources'][0]['chunkId'], 'company-1')
                    self.assertEqual(result['summary'], '수돗물 공급 업무를 해요.')
                else:
                    self.assertEqual(result['knowledgeSources'], [])
                self.assertIn('수돗물', model.call_args.args[2]['sources'][0]['text'])
                self.assertIn('짧은 두 문장 이내', model.call_args.args[1])
                self.assertEqual(model.call_args.kwargs['role'], 'regulation')

    def test_company_rejects_virtual_material(self):
        self.search_company.return_value = [self.company_hit(is_virtual=True)]
        with self.assertRaisesRegex(LlmError, '범주'):
            self.route('수자원공사 정보', self.response())

    def test_company_rejects_unknown_citation(self):
        self.search_company.return_value = [self.company_hit()]
        with self.assertRaisesRegex(LlmError, '출처'):
            self.route('수자원공사 정보', self.response(ids=['unknown']))

    def test_company_rejects_unsupported_number(self):
        self.search_company.return_value = [self.company_hit()]
        with self.assertRaisesRegex(LlmError, '숫자'):
            self.route('수자원공사 정보', self.response(summary='직원은 999명이에요.'))

    def test_unrelated_history_does_not_change_regulation_search(self):
        self.inp.update(history=[{'q': '교육비 기준은?', 'a': {'kind': 'regulation', 'basis': ['old-source']}}])
        self.route('사내 규정', self.response())
        self.search.assert_called_once_with(self.inp['question'], 5, '일반직', 'ollama')

    def test_follow_up_keeps_previous_question_for_classifier_and_search(self):
        self.inp.update(question='그럼 신청은 언제까지?', history=[{'q': '교육비 지원 기준은?', 'a': {'kind': 'regulation', 'basis': []}}])
        self.route('사내 규정', self.response())
        self.assertIn('교육비 지원', self.classify.call_args.args[0])
        self.assertEqual(self.search.call_count, 2)
        self.assertTrue(self.inp['_classification']['usedHistory'])

    def test_transport_error_is_not_refusal_or_no_evidence(self):
        with patch.object(rt, 'llm_json', side_effect=LlmError('Ollama 연결 실패: refused')):
            with self.assertRaisesRegex(LlmError, '연결 실패'):
                reg._api(self.ctx, self.inp)

    def test_actual_model_adapter_keeps_context_and_disables_sampling(self):
        settings = replace(reg.llm.S, ollama_url='http://test', ollama_num_ctx=16384)
        with patch.object(reg.llm, 'S', settings), patch.object(reg.llm, 'ollama', return_value={
                'message': {'content': json.dumps(self.response())}}) as remote:
            result = reg._api(self.ctx, self.inp)
        self.assertEqual(result['evidenceStatus'], 'found')
        payload = remote.call_args.args[1]
        self.assertEqual(payload['options'], {'num_gpu': -1, 'num_ctx': 16384, 'temperature': 0})
        self.assertIs(payload['think'], False)

    def test_malformed_model_json_is_error(self):
        with patch.object(reg.llm, 'ollama', return_value={'message': {'content': 'invalid JSON'}}):
            with self.assertRaisesRegex(LlmError, 'JSON'):
                reg._api(self.ctx, self.inp)

    def test_demo_mode_does_not_load_classifier(self):
        self.ctx.demo = True
        with patch.object(reg, '_mock', return_value=reg.ans(kind='out')), patch.object(rt, '_log'), patch.object(rt.time, 'sleep'):
            self.assertEqual(reg.answer(self.ctx, '질문', [], {})['kind'], 'out')
        self.classify.assert_not_called()

    def test_real_answer_exposes_classifier_metadata(self):
        self.classify.return_value = {'label': '범위 밖', 'confidence': 0.99}
        with patch.object(rt, '_log'):
            result = reg.answer(self.ctx, '오늘 날씨 어때?', [], {})
        self.assertEqual(result['kind'], 'out')
        self.assertEqual(self.ctx.meta['classification']['label'], '범위 밖')


if __name__ == '__main__':
    unittest.main()
