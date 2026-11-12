import io
import os
import unittest
from contextvars import Context
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app import browser_console as console, jobs, llm


class BrowserConsoleTests(unittest.TestCase):
    def setUp(self):
        token = console.options.set(console.BrowserOptions())
        self.addCleanup(console.options.reset, token)

    def test_bounds_and_server_permissions(self):
        headers = {'x-growpath-picker': 'off', 'x-growpath-timeout': '900',
                   'x-growpath-input': '131072', 'x-growpath-output': '32768'}
        self.assertEqual(console.from_headers(headers, True), console.BrowserOptions(True, False, 900, 131072, 32768))
        self.assertEqual(console.from_headers(headers, False), console.BrowserOptions(picker_off=True))
        self.assertIsNone(console.from_headers(dict(headers, **{'x-growpath-demo': 'off'}), True).timeout)
        for field, value in [('input', '0'), ('input', '131073'), ('output', '32769'), ('timeout', '901'), ('timeout', '1.5')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                console.from_headers({'x-growpath-' + field: value}, True)

    def test_runpod_address_and_key_validation(self):
        url = 'https://example-11434.proxy.runpod.net'
        headers = {'x-growpath-ollama-url': url + '/', 'x-growpath-ollama-key': 'fixture-key'}
        settings = console.from_headers(headers, True)
        self.assertEqual((settings.ollama_url, settings.ollama_key), (url, 'fixture-key'))
        self.assertNotIn('fixture-key', repr(settings))
        self.assertEqual(console.runpod_url('http://1.1.1.1:18123'), 'http://1.1.1.1:18123')
        self.assertIsNone(console.from_headers(headers, False).ollama_key)
        self.assertIsNone(console.from_headers({**headers, 'x-growpath-demo': 'off'}, True).ollama_url)
        for invalid in ('http://127.0.0.1:8080', url + '/test', url + '.example.org', 'http://1.1.1.1:65536'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                console.runpod_url(invalid)
        with self.assertRaises(ValueError):
            console.from_headers({'x-growpath-ollama-key': 'invalid key'}, True)

    def test_runpod_transport_isolated_from_default_credentials(self):
        url = 'https://example-11434.proxy.runpod.net'
        for custom_url, custom_key, expected in [
            (url, 'browser-fixture', 'browser-fixture'), (url, None, None),
            (None, 'browser-fixture', 'browser-fixture'), (None, None, 'env-fixture'),
        ]:
            with self.subTest(url=custom_url, key=bool(custom_key)), patch.object(llm, 'S', wraps=llm.S) as config, \
                 patch.object(llm.provider_keys, 'read', return_value=SimpleNamespace(value='env-fixture')) as shared, \
                 patch.object(llm, '_http', return_value=io.BytesIO(b'{}')) as transport:
                config.ollama_url = 'http://default.invalid'
                console.options.set(console.BrowserOptions(ollama_url=custom_url, ollama_key=custom_key))
                llm.ollama('api/chat', {})
                destination, _, headers, _ = transport.call_args.args
                self.assertEqual(destination, (custom_url or config.ollama_url) + '/api/chat')
                self.assertEqual(headers.get('Authorization'), 'Bearer ' + expected if expected else None)
                self.assertEqual(transport.call_args.kwargs.get('allow_redirects', True), not (custom_url or custom_key))
                self.assertEqual(shared.called, not (custom_url or custom_key))

    def test_http_settings_are_scoped_to_one_request(self):
        from dataclasses import replace
        from fastapi.testclient import TestClient
        from app import main
        from app.routers import account

        client = TestClient(main.app)
        config = replace(main.S, demo_mode=True, beta_account_picker=True)
        with patch.object(main, 'S', config), patch.object(account, 'S', config), patch.object(account.profile, 'accounts', return_value=[]):
            self.assertEqual(client.get('/api/v1/console/capabilities').json(), {'demo': True, 'picker': True})
            self.assertEqual(client.get('/api/v1/demo/accounts', headers={'X-GrowPath-Picker': 'off'}).status_code, 404)
            self.assertEqual(client.get('/api/v1/demo/accounts').status_code, 200)
            response = client.get('/api/v1/console/capabilities', headers={'X-GrowPath-Output': '0'})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()['error']['code'], 'INVALID_CONSOLE_OPTION')

    def test_job_preserves_originating_request_only(self):
        settings = console.BrowserOptions(timeout=180, input_tokens=8192, output_tokens=2048,
                                          ollama_url='https://example-11434.proxy.runpod.net', ollama_key='job-fixture')
        callback = Mock(side_effect=lambda ctx: self.assertEqual(console.options.get(), settings))
        with patch.object(jobs.db, 'tx'), patch.object(jobs.POOL, 'submit') as submit:
            token = console.options.set(settings)
            try:
                jobs.start('test', None, '', callback)
            finally:
                console.options.reset(token)
            worker = Context()
            worker.run(submit.call_args.args[0])
            self.assertEqual(worker.run(console.options.get), console.BrowserOptions())
        callback.assert_called_once()

    def test_provider_payload_timeout_and_reset(self):
        messages = [{'role': 'user', 'content': 'hello'}]
        token = console.options.set(console.BrowserOptions(timeout=180, input_tokens=8192, output_tokens=2048))
        with patch('app.catalog_budget.tokens', return_value=1), patch.object(llm, 'openai', return_value={'choices': [{'message': {}}]}) as openai:
            llm.chat('openai', messages)
            self.assertEqual(openai.call_args.kwargs['timeout'], 180)
            self.assertEqual(openai.call_args.args[1]['max_completion_tokens'], 2048)
            with patch.object(llm, 'S', wraps=llm.S) as config, patch.object(llm.provider_keys, 'read', return_value=SimpleNamespace(value='')), patch.object(llm, '_http', return_value=io.BytesIO(b'{"message":{"content":"ok"}}')) as http:
                config.ollama_url = 'http://test.invalid'
                config.ollama_model = 'model'
                llm.chat('ollama', messages)
                self.assertEqual(http.call_args.args[1]['options']['num_predict'], 2048)
                self.assertIs(http.call_args.args[1]['think'], False)
                self.assertEqual(http.call_args.args[3], 180)
            console.options.reset(token)
            llm.chat('openai', messages)
            self.assertNotIn('max_completion_tokens', openai.call_args.args[1])
            self.assertEqual(openai.call_args.kwargs['timeout'], 90)

    def test_over_budget_input_fails_before_network(self):
        from app.catalog_budget import FRAMING_RESERVE
        console.options.set(console.BrowserOptions(input_tokens=FRAMING_RESERVE + 1))
        with patch('app.catalog_budget.tokens', return_value=1), patch.object(llm, 'ollama') as send:
            with self.assertRaisesRegex(llm.LlmError, '한도'):
                llm.chat('ollama', [{'role': 'user', 'content': 'test'}])
            send.assert_not_called()
