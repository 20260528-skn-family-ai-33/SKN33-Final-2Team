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

    def run_route(self, label, response):
        self.classify.return_value = {'label': label}
        with patch.object(reg.regstore, 'search', return_value=[]) as search, \
             patch.object(reg.regstore, 'explicit_ref', return_value=None), \
             patch.object(rt, 'llm_json', return_value=response) as llm:
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

    def test_company_question_keeps_existing_general_answer_contract(self):
        result, search, llm = self.run_route('수자원공사 정보', {'kind': 'general', 'summary': '등록된 자료로 확인할 수 없어요.'})
        self.assertEqual(result['kind'], 'general')
        self.assertEqual(result['source'], 'work')
        search.assert_not_called()
        self.assertIn('자료에 없으면 확인할 수 없다고', llm.call_args.args[1])

    def test_llm_cannot_override_regulation_route(self):
        with self.assertRaisesRegex(LlmError, '답변 유형'):
            self.run_route('사내 규정', {'kind': 'general', 'summary': '답'})

    def test_llm_cannot_override_general_route(self):
        with self.assertRaisesRegex(LlmError, '답변 유형'):
            self.run_route('사내 생활안내', {'kind': 'regulation'})

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
