"""main의 공용 연결과 로컬 챗봇 JSON·로그 API 계약을 모의 HTTP로 함께 검사한다."""
import io
import json
import os
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import auth, browser_console, errors, llm, provider_keys, provider_policy
from app.agents import grounded_answer, runtime
from app.routers import account


class RunpodJsonIntegrationTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.settings = replace(llm.S, var_dir=Path(directory), ollama_url='', ollama_key='', demo_mode=True)
        for module in (llm, provider_policy, errors, account):
            self.enterContext(patch.object(module, 'S', self.settings))
        token = browser_console.options.set(browser_console.BrowserOptions())
        self.addCleanup(browser_console.options.reset, token)
        self.connection = provider_keys.RunpodConnection(
            'https://shared-fixture.proxy.runpod.net', provider_keys.Credential('shared-fixture-key', 'admin'), 'runpod', True)
        provider_keys.save_runpod(self.settings, self.connection)
        self.enterContext(patch.object(runtime, '_record_call'))
        self.enterContext(patch.object(provider_policy, 'selection', return_value=('employee', None)))
        self.enterContext(patch.object(provider_policy, 'current', return_value='employee'))
        app = FastAPI()
        app.include_router(account.r)
        app.add_exception_handler(errors.ApiError, errors.api_error_handler)
        self.client = self.enterContext(TestClient(app))
        self.identity = self.enterContext(patch.object(auth, 'account_of', return_value=auth.Account('admin', 1, '시험')))

    def test_shared_connection_and_model_schema_are_used_in_same_request(self):
        self.assertTrue(llm.available('ollama'))
        self.assertEqual(errors.unavailable_reason('ollama'), '')
        for topic in ('regulation', 'company', 'life'):
            for has_sources in (False, True):
                for status in grounded_answer.allowed_statuses(has_sources):
                    cited = status in ('found', 'partial')
                    response = {'status': status, 'summary': '확인한 내용 또는 확인할 수 없는 이유예요.',
                                'sourceIds': ['S001'] if cited else []}
                    sources = [{'id': 'doc-1', 'text': '공개 이용 안내'}] if has_sources else []
                    wire = json.dumps({'message': {'content': json.dumps(response, ensure_ascii=False)}}).encode()
                    with self.subTest(topic=topic, has_sources=has_sources, status=status):
                        with patch.object(llm, '_http', return_value=io.BytesIO(wire)) as send:
                            result = grounded_answer.generate(runtime.Ctx(1), topic, '질문', sources, {})
                        send.assert_called_once()
                        url, payload, headers, _ = send.call_args.args
                        self.assertEqual(url, self.connection.url + '/api/chat')
                        self.assertEqual(headers['Authorization'], 'Bearer shared-fixture-key')
                        self.assertIs(send.call_args.kwargs['allow_redirects'], False)
                        schema = payload['format']
                        self.assertEqual(schema['required'], ['status', 'summary', 'sourceIds'])
                        self.assertEqual(set(schema['properties']), set(response))
                        self.assertFalse(schema['additionalProperties'])
                        self.assertEqual(schema['properties']['status']['enum'],
                                         ['refused', 'no_match', 'partial', 'found'] if has_sources
                                         else ['refused', 'not_found'])
                        if not has_sources:
                            self.assertEqual(schema['properties']['sourceIds']['maxItems'], 0)
                        self.assertEqual(result, dict(response, sourceIds=['doc-1'] if cited else []))

    def test_ollama_wire_format_errors_remain_distinct_from_valid_empty_evidence(self):
        cases = [
            ('{"summary":"안내","sourceIds":[]}', '근거 확인 상태를 읽을 수'),
            ('{"status":"found|partial|not_found|refused","summary":"안내","sourceIds":[]}', '근거 확인 상태를 읽을 수'),
            ('{"status":"no_match","summary":" ","sourceIds":[]}', '이유가 비어'),
            ('{"status":"found","summary":"안내","sourceIds":["S999"]}', '검색 자료에 없는 출처'),
            ('{"status":', 'JSON 형식'),
        ]
        for topic in ('regulation', 'company', 'life'):
            for content, expected_error in cases:
                with self.subTest(topic=topic, content=content):
                    wire = json.dumps({'message': {'content': content}}).encode()
                    with patch.object(llm, '_http', return_value=io.BytesIO(wire)) as send:
                        with self.assertRaisesRegex(llm.LlmError, expected_error):
                            grounded_answer.generate(runtime.Ctx(1), topic, '질문',
                                                     [{'id': 'doc-1', 'text': '공개 이용 안내'}], {})
                    send.assert_called_once()

    def test_admin_provider_info_and_ping_use_shared_connection_despite_browser_override(self):
        browser_console.options.set(browser_console.BrowserOptions(
            ollama_url='https://browser-fixture.proxy.runpod.net', ollama_key='browser-fixture-key'))
        provider = self.client.get('/api/v1/ai/providers').json()['providers'][0]
        self.assertTrue(provider['available'])
        self.assertEqual((provider['reason'], provider['target']), ('', 'runpod'))
        with patch.object(llm, 'ping', return_value={'ok': True}) as ping:
            self.assertEqual(self.client.get('/api/v1/ai/status').status_code, 200)
        self.assertEqual(ping.call_args.kwargs['connection'].url, self.connection.url)
        self.assertEqual(ping.call_args.kwargs['connection'].key.value, 'shared-fixture-key')

    def test_employee_connection_uses_browser_override_without_shared_key(self):
        browser_console.options.set(browser_console.BrowserOptions(
            ollama_url='https://browser-fixture.proxy.runpod.net'))
        chosen = llm.ollama_connection()
        self.assertEqual(chosen.url, 'https://browser-fixture.proxy.runpod.net')
        self.assertEqual(chosen.key.value, '')
        self.assertEqual(provider_keys.runpod(self.settings).key.value, 'shared-fixture-key')

    def test_reset_restores_environment_and_previous_admin_key(self):
        settings = replace(self.settings, ollama_url='http://environment.invalid', ollama_key='env-fixture')
        provider_keys.save(settings, 'ollama', 'legacy-admin-fixture')
        provider_keys.reset_runpod(settings)
        restored = provider_keys.runpod(settings)
        self.assertEqual(restored.url, settings.ollama_url)
        self.assertEqual(restored.key.value, 'legacy-admin-fixture')
        self.assertFalse(restored.managed)

    def test_invalid_shared_record_is_not_silently_replaced_with_environment(self):
        Path(self.settings.var_dir, 'provider-keys', 'runpod.json').write_text('invalid', encoding='ascii')
        with self.assertRaises(json.JSONDecodeError):
            llm.ollama_connection()


if __name__ == '__main__':
    unittest.main()
