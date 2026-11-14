"""외부 연결 없이 챗봇 단계·실패 위치·원문 보존·동시 요청 격리를 검사한다."""
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from threading import Barrier
from unittest.mock import Mock, patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app import llm
from app.agents import regulation as reg, runtime as rt
from app.errors import AgentError


class AssistantStageLogTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(rt._logs, clear=True))
        self.enterContext(patch.object(rt.db, 'tx', side_effect=lambda: nullcontext(Mock())))
        self.enterContext(patch.object(llm, 'available', return_value=True))
        self.enterContext(patch.object(llm, 'model_name', return_value='test-model'))
        self.classifier = self.enterContext(patch.object(reg.question_classifier, 'classify', return_value={
            'label': '사내 생활안내', 'confidence': 0.95, 'model': 'test-classifier'}))
        self.hits = [{'chunk_id': 'doc-1', 'document_id': 'guide', 'document_title': '생활안내',
                      'chunk_text': '통근버스 안내', 'chunk_text_sha256': 'a' * 64,
                      'is_virtual': True, 'metadata': {}}]
        self.sources = [{'id': 'doc-1', 'text': '시간표는 사내 포털에서 확인합니다.', 'document': '생활안내'}]
        self.retrieve = self.enterContext(patch.object(reg, 'retrieve_knowledge_slots',
                                                       return_value=(self.hits, self.sources)))
        self.response = {'status': 'partial', 'summary': '시간표는 사내 포털에서 확인해 주세요.', 'sourceIds': ['S001']}
        self.chat = self.enterContext(patch.object(llm, 'chat', return_value={
            'content': json.dumps(self.response, ensure_ascii=False), 'model': 'test-model'}))

    def ask(self, provider='ollama'):
        ctx = rt.Ctx(7, provider=provider, me={'empGroup': '일반직'})
        history = [{'q': '교육비 지원을 받을 수 있나요?', 'a': {'summary': '교육비 지원 안내'}},
                   {'q': '통근버스 시간표는 어디서 봐요?', 'a': {'summary': '사내 포털에서 확인합니다.'}}]
        return reg.answer(ctx, '몇시부터 몇시 운영하는데요?', history, {}, documents_only=True)

    def latest(self):
        return rt.all_logs()[0]

    def test_success_in_both_providers_keeps_steps_and_call_association(self):
        for provider in ('ollama', 'openai'):
            with self.subTest(provider=provider), self.assertLogs(rt.logger, level='INFO') as logged:
                result = self.ask(provider)
            entry = self.latest()
            self.assertEqual(result['evidenceStatus'], 'partial')
            self.assertEqual([s['id'] for s in entry['stages']], [
                '1.classify', '2.reclassify', '3-2.retrieve', '4-2.generate',
                '4-2.generate.model', '4-2.generate.parse', '4.contract', '5-2.validate'])
            self.assertTrue(all(s['status'] == 'ok' and s['ms'] >= 0 for s in entry['stages']))
            self.assertNotIn('failedStage', entry)
            self.assertEqual(entry['calls'][0]['stageId'], '4-2.generate')
            self.assertEqual(entry['stages'][6]['parentId'], '4-2.generate')
            self.assertTrue(all(entry['traceId'] in line for line in logged.output))
            self.assertNotIn('몇시부터', '\n'.join(logged.output))
            self.assertNotIn(self.response['summary'], '\n'.join(logged.output))

    def test_model_parse_and_contract_failures_are_distinct_and_preserve_raw_output(self):
        cases = [
            ('4-2.generate.model', llm.LlmError('Ollama 시간 초과: 민감한 예외 원문'), None),
            ('4-2.generate.parse', None, 'JSON이 아닌 민감한 원문'),
            ('4.contract', None, '{"summary":"민감한 응답","kind":"general"}'),
            ('4.contract', None, '{"status":"wrong","summary":"민감한 응답"}'),
        ]
        for provider in ('ollama', 'openai'):
            for failed_id, error, content in cases:
                with self.subTest(provider=provider, stage=failed_id, content=content):
                    self.chat.side_effect = error
                    self.chat.return_value = {'content': content, 'model': 'test-model'}
                    with self.assertLogs(rt.logger, level='INFO') as logged, self.assertRaises(AgentError) as raised:
                        self.ask(provider)
                    entry = self.latest()
                    self.assertEqual(entry['failedStage']['id'], failed_id)
                    self.assertEqual(raised.exception.info['failedStage'], entry['failedStage'])
                    self.assertEqual(raised.exception.info['traceId'], entry['traceId'])
                    self.assertEqual(entry['calls'][0]['output'], content or '')
                    self.assertNotIn('5-2.validate', [s['id'] for s in entry['stages']])
                    self.assertNotIn('민감한', '\n'.join(logged.output))
                    self.assertIsNone(rt._stage.get())
                    if failed_id == '4.contract':
                        contract = next(s for s in entry['stages'] if s['id'] == failed_id)
                        self.assertFalse(contract['statusValid'])
                        self.assertIn('근거 확인 상태', str(raised.exception))

    def test_pipeline_stops_at_first_failed_step(self):
        cases = [('classify_question_roberta', '1.classify'),
                 ('verify_or_reclassify_label_with_llm', '2.reclassify'),
                 ('retrieve_knowledge_slots', '3-2.retrieve'),
                 ('generate_knowledge_summary', '4-2.generate'),
                 ('format_knowledge_response', '5-2.validate')]
        for target, failed_id in cases:
            with self.subTest(target=target), patch.object(reg, target, side_effect=llm.LlmError('시험 실패')):
                with self.assertLogs(rt.logger, level='INFO'), self.assertRaises(AgentError):
                    self.ask()
                entry = self.latest()
                self.assertEqual(entry['failedStage']['id'], failed_id)
                self.assertEqual(entry['stages'][-1]['id'], failed_id)
                self.assertEqual(entry['stages'][-1]['status'], 'failed')

    def test_low_confidence_records_reclassification_model_call(self):
        self.classifier.return_value['confidence'] = 0.5
        self.chat.side_effect = [
            {'content': '{"label":"사내 생활안내"}', 'model': 'test-model'},
            {'content': json.dumps(self.response), 'model': 'test-model'}]
        with self.assertLogs(rt.logger, level='INFO'):
            self.ask()
        entry = self.latest()
        self.assertEqual([c['stageId'] for c in entry['calls']], ['2.reclassify', '4-2.generate'])
        self.assertTrue(entry['stages'][1]['modelRequired'])

    def test_regulation_and_out_of_scope_branches_are_logged(self):
        for label in ('사내 규정', '범위 밖', '수자원공사 정보'):
            with self.subTest(label=label):
                self.classifier.return_value['label'] = label
                with (patch.object(reg, 'retrieve_regulation_slots', return_value=['r1']),
                      patch.object(reg, 'generate_regulation_summary', return_value={}),
                      patch.object(reg, 'format_regulation_response', return_value={'kind': 'regulation'}),
                      self.assertLogs(rt.logger, level='INFO')):
                    self.ask()
                ids = [s['id'] for s in self.latest()['stages']]
                expected = '5.out' if label == '범위 밖' else '5-1.validate' if label == '사내 규정' else '5-2.validate'
                self.assertEqual(ids[-1], expected)
                if label == '범위 밖':
                    self.assertEqual(ids, ['1.classify', '2.reclassify', '5.out'])

    def test_empty_search_records_generation_and_keeps_not_found_or_refused(self):
        self.retrieve.return_value = ([], [])
        for provider in ('ollama', 'openai'):
            for status in ('not_found', 'refused'):
                with self.subTest(provider=provider, status=status):
                    self.chat.reset_mock()
                    response = {'status': status, 'summary': '확인할 수 없는 이유예요.', 'sourceIds': []}
                    self.chat.return_value['content'] = json.dumps(response)
                    with self.assertLogs(rt.logger, level='INFO'):
                        result = self.ask(provider)
                    self.assertEqual(result['evidenceStatus'], status)
                    self.assertEqual(result['summary'], response['summary'])
                    self.chat.assert_called_once()
                    entry = self.latest()
                    self.assertEqual(entry['stages'][2]['sourceCount'], 0)
                    self.assertEqual([call['stageId'] for call in entry['calls']], ['4-2.generate'])
                    self.assertTrue(all(step['status'] == 'ok' for step in entry['stages']))
                    self.assertNotIn('failedStage', entry)

    def test_empty_search_keeps_reclassification_and_answer_model_calls(self):
        self.classifier.return_value['confidence'] = 0.5
        self.retrieve.return_value = ([], [])
        self.chat.side_effect = [
            {'content': '{"label":"사내 생활안내"}', 'model': 'test-model'},
            {'content': '{"status":"not_found","summary":"이번 자료에서 확인하지 못했어요.","sourceIds":[]}', 'model': 'test-model'}]
        with self.assertLogs(rt.logger, level='INFO'):
            result = self.ask()
        self.assertEqual(self.chat.call_count, 2)
        self.assertEqual(result['evidenceStatus'], 'not_found')
        self.assertEqual([call['stageId'] for call in self.latest()['calls']], ['2.reclassify', '4-2.generate'])
        self.assertIn('4-2.generate.model', [step['id'] for step in self.latest()['stages']])

    def test_uncited_states_with_sources_are_preserved_without_conversion(self):
        reason = '검색된 자료로 운영 시간을 확인하지 못했어요. 담당자에게 문의하세요.'
        for status in ('not_found', 'no_match'):
            self.chat.return_value['content'] = json.dumps({
                'status': status, 'summary': reason, 'sourceIds': []})
            for provider in ('ollama', 'openai'):
                with self.subTest(provider=provider, status=status), self.assertLogs(rt.logger, level='INFO'):
                    result = self.ask(provider)
                self.assertEqual(result['evidenceStatus'], status)
                self.assertEqual(result['summary'], reason)
                self.assertEqual(result['knowledgeSources'], [])
                self.assertEqual(self.latest()['stages'][2]['sourceCount'], 1)
                self.assertNotIn('failedStage', self.latest())
                self.assertTrue(all(step['status'] == 'ok' for step in self.latest()['stages']))
                contract = next(step for step in self.latest()['stages'] if step['id'] == '4.contract')
                self.assertTrue(contract['statusValid'])

    def test_unexpected_exception_is_not_replaced(self):
        error = ValueError('민감한 원문')
        with patch.object(reg, 'retrieve_knowledge_slots', side_effect=error):
            with self.assertLogs(rt.logger, level='INFO') as logged, self.assertRaises(ValueError) as raised:
                self.ask()
        self.assertIs(raised.exception, error)
        self.assertEqual(self.latest()['failedStage']['id'], '3-2.retrieve')
        self.assertNotIn('민감한 원문', '\n'.join(logged.output))

    def test_concurrent_runs_keep_distinct_traces_and_stages(self):
        barrier = Barrier(2)

        def work(number):
            ctx = rt.Ctx(number)

            def live(_):
                with rt.stage(ctx, f'test-{number}', '동시 요청 격리'):
                    barrier.wait(timeout=5)
                return {}

            rt.run(ctx, '시험', '시험', {}, None, live)

        with self.assertLogs(rt.logger, level='INFO'), ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(work, [11, 12]))
        entries = rt.all_logs()
        self.assertEqual(len({e['traceId'] for e in entries}), 2)
        for entry in entries:
            self.assertEqual([s['id'] for s in entry['stages']], [f"test-{entry['employeeId']}"])


if __name__ == '__main__':
    unittest.main()
