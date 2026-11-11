"""'에이전트 동작 보기' 기록: 모델을 바로 부르는 곳도 빠짐없이, 입력·출력은 자르지 않고 남긴다."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')
from contextlib import nullcontext
from dataclasses import replace
import json
import unittest
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import auth, llm
from app.agents import runtime as rt
from app.errors import AgentError, ApiError, api_error_handler
from app.routers import account

LONG = '가' * 5000  # 이전 기록은 1600자에서 잘랐다


class AgentLogTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(rt._logs, clear=True))
        self.insert = Mock()
        self.enterContext(patch.object(rt.db, 'tx', side_effect=lambda: nullcontext(self.insert)))
        self.enterContext(patch.object(rt.llm, 'available', return_value=True))
        self.ctx = rt.Ctx(7, provider='openai')

    def chat(self, content):
        return patch.object(rt.llm, 'chat', return_value={'content': content, 'model': 'gpt-test', 'loadMs': 0})

    def test_direct_model_call_is_logged_with_name_and_full_text(self):
        with self.chat(json.dumps({'answer': LONG}, ensure_ascii=False)):
            out = rt.model(self.ctx, '진단 에이전트', '역량 테스트 문항 생성')('시스템 ' + LONG, {'goal': LONG})
        self.assertEqual(out, {'answer': LONG})
        [e] = rt.all_logs()
        self.assertEqual((e['agent'], e['task'], e['mode'], e['employeeId']), ('진단 에이전트', '역량 테스트 문항 생성', 'api', 7))
        [call] = e['calls']
        self.assertEqual(call['system'], '시스템 ' + LONG)
        self.assertEqual(json.loads(call['messages'][-1]['content']), {'goal': LONG})
        self.assertEqual(json.loads(call['output']), {'answer': LONG})
        self.assertEqual(call['model'], 'gpt-test')
        self.assertNotIn('error', e)
        self.insert.run.assert_called_once()  # DB 에는 메타데이터 한 줄

    def test_model_calls_inside_run_attach_to_that_run_only(self):
        def live(_):
            first = rt.llm_json(self.ctx, '첫 지시', {'n': 1})
            second = rt.llm_json(self.ctx, '고치기 지시', {'n': 2})
            return {'items': [first, second], 'long': LONG}
        with self.chat('{"ok": true}'):
            out = rt.run(self.ctx, '진단 에이전트', '사전 점검 문항 생성', {'goal': LONG}, None, live)
        [e] = rt.all_logs()
        self.assertEqual([c['system'] for c in e['calls']], ['첫 지시', '고치기 지시'])
        self.assertIn(LONG, e['input'])
        self.assertEqual(json.loads(e['output']), out)
        self.assertEqual(self.insert.run.call_count, 1)
        # run 이 끝난 뒤의 호출은 다시 따로 남는다
        with self.chat('{}'):
            rt.llm_json(self.ctx, '나중 지시', {})
        self.assertEqual(rt.all_logs()[0]['task'], '이름 없는 호출 · default')

    def test_failed_direct_call_keeps_raw_response_and_original_error(self):
        with self.chat('JSON 이 아닌 답 ' + LONG), self.assertRaises(llm.LlmError):
            rt.model(self.ctx, '자료 추천', '스킬별 학습 자료 추천', role='resources')('지시', {})
        with patch.object(rt.llm, 'chat', side_effect=llm.LlmError('OpenAI 시간 초과')), self.assertRaises(llm.LlmError):
            rt.model(self.ctx, '진단 에이전트', '목표 스킬 선정')('지시', {})
        timeout, not_json = rt.all_logs()
        self.assertEqual((not_json['mode'], not_json['calls'][0]['output']), ('error', 'JSON 이 아닌 답 ' + LONG))
        self.assertEqual(not_json['calls'][0]['role'], 'resources')
        self.assertEqual(timeout['error'], 'OpenAI 시간 초과')
        self.assertTrue(timeout['kind'])

    def test_run_logs_other_exceptions_without_changing_them(self):
        def live(_):
            rt.llm_json(self.ctx, '지시', {})
            raise ApiError(422, 'SKILLS_INVALID', '검증 실패')
        with self.chat('{}'), self.assertRaises(ApiError):
            rt.run(self.ctx, '로드맵 계획 · A1', '로드맵 생성', {}, None, live)
        [e] = rt.all_logs()
        self.assertEqual((e['mode'], e['error']), ('error', 'ApiError: 검증 실패'))
        self.assertEqual(len(e['calls']), 1)
        with self.assertRaises(AgentError):
            rt.run(replace(self.ctx, fail_sim={'goal': True}), '진단 에이전트', '목표 후보', {}, None, live, sim='시연 실패', mock_delay=0)
        self.assertEqual(rt.all_logs()[0]['mode'], 'sim')

    def test_images_are_counted_not_stored(self):
        with self.chat('{}'):
            rt.llm_json(self.ctx, '지시', {'fileName': 'a.png'}, role='vision', images=[{'b64': 'QUJD' * 1000}] * 2)
        [call] = rt.all_logs()[0]['calls']
        self.assertEqual(call['images'], 2)
        self.assertNotIn('QUJD', json.dumps(call))


class AgentLogApiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(account.r)
        app.add_exception_handler(ApiError, api_error_handler)
        self.client = TestClient(app)
        self.enterContext(patch.object(account, 'S', replace(account.S, demo_mode=True)))
        self.enterContext(patch.object(auth, 'account_of', return_value=auth.Account('employee', 1, 'test')))
        self.enterContext(patch.object(account.db, 'all_', return_value=[{'employee_id': 7, 'name': '시험 직원'}]))
        self.entry = {'id': 3, 't': 10, 'employeeId': 7, 'agent': '진단 에이전트', 'task': '역량 테스트 문항 생성', 'mode': 'api', 'ms': 5,
                      'input': LONG, 'output': LONG, 'calls': [{'system': LONG, 'messages': [], 'output': LONG}]}

    def test_list_has_summaries_and_detail_has_full_text(self):
        with patch.object(rt, 'all_logs', return_value=[self.entry]):
            [row] = self.client.get('/api/v1/ai/log').json()['log']
        self.assertEqual(row, {'id': 3, 'employeeId': 7, 'employee': '시험 직원', 'agent': '진단 에이전트', 'task': '역량 테스트 문항 생성',
                               'mode': 'api', 'ms': 5, 'callCount': 1})
        with patch.object(rt, 'log_entry', return_value=self.entry) as find:
            detail = self.client.get('/api/v1/ai/log/3').json()
        find.assert_called_once_with(3)
        self.assertEqual((detail['input'], detail['output'], detail['calls'][0]['system']), (LONG, LONG, LONG))
        self.assertEqual(detail['employee'], '시험 직원')
        self.assertNotIn('t', detail)

    def test_missing_detail_is_404_and_demo_off_hides_it(self):
        with patch.object(rt, 'log_entry', return_value=None):
            response = self.client.get('/api/v1/ai/log/99')
        self.assertEqual((response.status_code, response.json()['error']['code']), (404, 'LOG_NOT_FOUND'))
        with patch.object(account, 'S', replace(account.S, demo_mode=False)), patch.object(rt, 'log_entry') as find:
            self.assertEqual(self.client.get('/api/v1/ai/log/3').status_code, 404)
        find.assert_not_called()

    def test_lookup_finds_entries_of_any_account(self):
        with patch.dict(rt._logs, clear=True):
            rt._logs[7] = rt.deque([{'id': 1}, {'id': 2}])
            rt._logs[None] = rt.deque([{'id': 5}])
            self.assertEqual(rt.log_entry(5), {'id': 5})
            self.assertIsNone(rt.log_entry(4))


if __name__ == '__main__':
    unittest.main()
