"""관리자 전환부터 에이전트의 실제 HTTP 요청 형식까지 검증한다."""
import io
import json
import os
import threading
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, browser_console, errors, llm, provider_keys, provider_policy
from app.agents import runtime
from app.errors import ApiError, api_error_handler
from app.routers import account, admin
from app.services import goals


class ProviderPolicyTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(admin.r)
        app.include_router(account.r)
        app.add_exception_handler(ApiError, api_error_handler)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.directory = self.enterContext(TemporaryDirectory())
        self.settings = replace(llm.S, var_dir=Path(self.directory), employee_ai_selection=True,
                                openai_key='example-openai', ollama_key='example-ollama',
                                ollama_url='http://localhost', demo_mode=False)
        for module in (provider_policy, llm, account, runtime, admin, errors, goals):
            self.enterContext(patch.object(module, 'S', self.settings))
        self.identity = self.enterContext(patch.object(auth, 'account_of', return_value=auth.Account('admin', 1, 'test')))
        self.enterContext(patch.object(runtime.db, 'one', return_value={'ai_provider': 'ollama'}))

    def save(self, mode):
        return self.client.put('/api/v1/admin/ai-provider', json={'policy': mode})

    def test_shared_runpod_check_save_read_and_restore(self):
        endpoint = '/api/v1/admin/ai-provider/ollama/connection'
        url = 'https://team-11434.proxy.runpod.net'
        draft = {'url': url + '/', 'key': 'test-pod-key'}
        provider_keys.save(self.settings, 'ollama', 'previous-key')
        models = [self.settings.ollama_model, self.settings.ollama_model_regulation]
        installed = list(models)
        denied = False

        def transport(destination, payload, headers, timeout, *, allow_redirects):
            self.assertFalse(allow_redirects)
            self.assertTrue(destination.startswith(url + '/api/'))
            self.assertEqual(headers.get('Authorization'), 'Bearer test-pod-key')
            if denied:
                raise HTTPError(destination, 401, 'Unauthorized', {}, io.BytesIO(b''))
            result = {'version': '0.40', 'models': [{'name': n + ':latest'} for n in installed]}
            return io.BytesIO(json.dumps(result).encode())

        with patch.object(llm, '_http', side_effect=transport):
            token = browser_console.options.set(browser_console.BrowserOptions(ollama_url='https://personal.proxy.runpod.net', ollama_key='personal-key'))
            try:
                response = self.client.post(endpoint + '/check', json=draft)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual([m['name'] for m in response.json()['models']], models)
                self.assertFalse(provider_keys.runpod(self.settings).managed)
                denied = True
                self.assertEqual(self.client.put(endpoint, json=draft).status_code, 502)
                self.assertFalse(provider_keys.runpod(self.settings).managed)
                denied = False
                installed.pop()
                failed = self.client.put(endpoint, json=draft)
                self.assertEqual(failed.status_code, 409)
                self.assertIn(models[-1], failed.json()['error']['message'])
                self.assertFalse(provider_keys.runpod(self.settings).managed)
                installed.append(models[-1])
                saved = self.client.put(endpoint, json=draft)
                self.assertEqual(saved.status_code, 200, saved.text)
                self.assertEqual(saved.json()['runpod'], {'url': url, 'managed': True})
                self.assertNotIn(draft['key'], saved.text)
                self.assertEqual(self.client.post(endpoint + '/check', json={}).status_code, 200)
                self.assertEqual(self.client.get('/api/v1/ai/status?provider=ollama').status_code, 200)
            finally:
                browser_console.options.reset(token)
            self.assertEqual(provider_policy.current(), 'employee')
            llm.ollama('api/chat', {'messages': []})
        with patch.object(llm, 'S', replace(self.settings, ollama_url='')):
            self.assertTrue(llm.available('ollama'))
            self.assertEqual(llm.ollama_connection().target, 'runpod')
        self.assertEqual(self.client.delete(endpoint).status_code, 200)
        restored = provider_keys.runpod(self.settings)
        self.assertEqual((restored.url, restored.key.value), (self.settings.ollama_url, 'previous-key'))

    def test_runpod_input_and_permissions(self):
        endpoint = '/api/v1/admin/ai-provider/ollama/connection'
        draft = {'url': 'https://team.proxy.runpod.net', 'key': 'test-only-secret'}
        with patch.object(llm, '_http') as send:
            for body in ({**draft, 'url': 'http://127.0.0.1:8080'}, {**draft, 'key': ['test-only-secret']}, {'url': draft['url']}):
                response = self.client.put(endpoint, json=body)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn('test-only-secret', response.text)
            for account, code in ((auth.Account('employee', 1, 'employee'), 403), (None, 401)):
                self.identity.return_value = account
                self.assertEqual(self.client.put(endpoint, json=draft).status_code, code)
                self.assertEqual(self.client.post(endpoint + '/check', json=draft).status_code, code)
                self.assertEqual(self.client.delete(endpoint).status_code, code)
            send.assert_not_called()

    def test_personal_url_cannot_enable_shared_policy(self):
        settings = replace(self.settings, ollama_url='')
        with patch.object(provider_policy, 'S', settings), patch.object(llm, 'S', settings):
            token = browser_console.options.set(browser_console.BrowserOptions(ollama_url='https://personal.proxy.runpod.net'))
            try:
                self.assertTrue(llm.available('ollama'))
                self.assertEqual(self.save('ollama').status_code, 409)
                self.assertEqual(provider_policy.current(), 'employee')
            finally:
                browser_console.options.reset(token)

    def test_permissions_missing_key_and_invalid_choice_preserve_policy(self):
        self.assertEqual(self.save('ollama').status_code, 200)
        with patch.object(llm, 'S', replace(self.settings, openai_key='')):
            self.assertEqual(self.save('openai').status_code, 409)
        self.assertEqual(self.save('other').status_code, 422)
        self.assertEqual(provider_policy.current(), 'ollama')
        response = self.client.get('/api/v1/admin/ai-provider')
        self.assertTrue(response.json()['providers']['openai']['keyConfigured'])
        self.assertNotIn(self.settings.openai_key, response.text)
        self.assertNotIn(self.settings.ollama_key, response.text)
        self.assertEqual(Path(self.directory, 'ai-provider').read_text().strip(), 'ollama')
        self.identity.return_value = auth.Account('employee', 1, 'team lead')
        self.assertEqual(self.save('openai').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/admin/ai-provider').status_code, 403)
        self.assertEqual(self.client.put('/api/v1/me/ai-provider', json={'provider': 'openai'}).status_code, 409)
        self.assertEqual(self.client.put('/api/v1/me/reasoning', json={'provider': 'ollama', 'level': None}).status_code, 409)
        self.identity.return_value = None
        self.assertEqual(self.save('openai').status_code, 401)

    def test_admin_repairs_invalid_file_without_enabling_inference_or_bulk_work(self):
        path = Path(self.directory, 'ai-provider')
        endpoint = '/api/v1/admin/ai-provider'
        for raw in (b'', b'unknown\n', b'employee\nhigh\n', b'\xff'):
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                self.assertEqual(self.client.get('/api/v1/me').status_code, 200)  # 관리자 로그인 유지
                state = self.client.get(endpoint).json()
                self.assertEqual((state['policy'], state['level'], state['policyStatus']), (None, None, 'invalid'))
                with self.assertRaises(ApiError) as err:
                    runtime.context(1, {})
                self.assertEqual((err.exception.status, err.exception.code), (503, 'BAD_PROVIDER_POLICY'))
                with patch.object(admin.db, 'all_') as employees:
                    self.assertEqual(self.client.post('/api/v1/admin/goal-suggestions/regenerate-all', json={}).status_code, 503)
                    employees.assert_not_called()
                self.assertEqual(self.save('unknown').status_code, 422)
                self.assertEqual(path.read_bytes(), raw)
                self.identity.return_value = auth.Account('employee', 1, 'test')
                self.assertEqual(self.save('openai').status_code, 403)
                self.identity.return_value = auth.Account('admin', 1, 'test')
                response = self.client.put(endpoint, json={'policy': 'openai', 'level': 'high'})
                self.assertEqual(response.json()['policyStatus'], 'active')
                self.assertEqual(self.save('openai').json()['level'], 'high')  # 이전 클라이언트 호환
                self.assertEqual(runtime.context(1, {}).reasoning, {'openai': 'high'})

    def test_private_key_rotation_and_permissions(self):
        path = '/api/v1/admin/ai-provider/openai/key'
        def info(response):
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('test-replacement', response.text)
            self.assertNotIn(self.settings.openai_key, response.text)
            return response.json()['providers']['openai']
        self.assertEqual(info(self.client.put(path, json={'key': 'test-replacement'}))['keySource'], 'admin')
        self.assertEqual(provider_keys.read(self.settings, 'openai').value, 'test-replacement')
        target = self.settings.var_dir / 'provider-keys/openai'
        if os.name == 'posix':
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        invalid = self.client.put(path, json={'key': 'test-replacement bad'})
        self.assertEqual(invalid.status_code, 422)
        self.assertNotIn('test-replacement', invalid.text)
        for actor, status in ((auth.Account('employee', 1, 'test'), 403), (None, 401)):
            self.identity.return_value = actor
            self.assertEqual(self.client.put(path, json={'key': 'other'}).status_code, status)
            self.assertEqual(self.client.delete(path).status_code, status)
        self.assertEqual(provider_keys.read(self.settings, 'openai').value, 'test-replacement')
        self.identity.return_value = auth.Account('admin', 1, 'test')
        self.assertEqual(info(self.client.delete(path))['keySource'], 'env')
        self.assertFalse(target.exists())

    def test_openai_without_env_key_can_be_enabled_and_reset(self):
        settings = replace(self.settings, openai_key='')
        with patch.object(llm, 'S', settings), patch.object(admin, 'S', settings), patch.object(errors, 'S', settings):
            path = '/api/v1/admin/ai-provider/openai/key'
            self.assertFalse(llm.available('openai'))
            saved = self.client.put(path, json={'key': 'local-test-key'}).json()['providers']['openai']
            self.assertEqual((saved['keySource'], saved['hasDefaultKey'], saved['available']), ('admin', False, True))
            self.assertEqual(self.save('openai').status_code, 200)
            self.assertEqual(self.client.delete(path).json()['providers']['openai']['keySource'], 'none')
            self.assertFalse(llm.available('openai'))

    def test_bulk_uses_displayed_policy_and_rejects_a_stale_confirmation(self):
        from app.services import goals
        path = '/api/v1/admin/goal-suggestions/regenerate-all'
        with patch.object(admin.db, 'all_', return_value=[{'employee_id': 7}]), patch.object(goals, 'request') as start:
            for policy in ('employee', 'ollama', 'openai'):
                self.save(policy)
                result = self.client.post(path, json={'expectedPolicy': policy, 'employeeIds': [7]})
                self.assertEqual(result.json()['mode'], policy)
                self.assertEqual(start.call_args.args, (7, 'admin-pick'))
                self.assertEqual(start.call_args.kwargs['approved_model']['provider'],
                                 'ollama' if policy == 'employee' else policy)
                start.reset_mock()
            self.assertEqual(self.client.post(path, json={'expectedPolicy': 'ollama'}).status_code, 409)
            start.assert_not_called()

    def test_employee_preferences_restore_when_admin_releases_policy(self):
        def employee_settings():
            self.identity.return_value = auth.Account('employee', 1, 'test')
            return self.client.get('/api/v1/ai/providers').json()

        with patch.object(account.db, 'one', return_value={'ai_provider': 'ollama', 'reasoning': {'ollama': 'low'}}):
            self.save('openai')
            fixed = employee_settings()
            self.assertEqual((fixed['current'], fixed['employeeReasoning']), ('openai', {}))
            self.identity.return_value = auth.Account('admin', 1, 'test')
            self.save('employee')
            restored = employee_settings()
            self.assertEqual((restored['current'], restored['employeeReasoning']), ('ollama', {'ollama': 'low'}))

    def test_queued_and_recovered_bulk_use_the_selection_at_confirmation(self):
        from types import SimpleNamespace
        from app.services import job_recovery

        employees = [{'employee_id': n, 'ai_provider': 'openai', 'reasoning': {'openai': 'high'}} for n in range(1, 10)]
        route = '/api/v1/admin/goal-suggestions/regenerate-all'
        queued = []

        def enqueue(kind, employee, ref, work, **kwargs):
            queued.append(work)
            return 'job'

        def call_model(ctx, *args, **kwargs):
            runtime.llm_json(ctx, 'Return JSON', {})
            return {'candidates': []}

        with (patch.object(goals.db, 'tx') as tx, patch.object(admin.db, 'all_', return_value=employees),
              patch.object(goals.profile, 'view', return_value={'job': 'engineer'}),
              patch.object(goals.jobs, 'start', side_effect=enqueue), patch.object(goals.G, 'run', side_effect=call_model),
              patch.object(llm, 'chat', return_value={'content': '{"ok":true}'}) as chat):
            tx.return_value.__enter__.return_value.one.return_value = {}
            for policy, level, expected, effort in [('ollama', None, 'ollama', None), ('openai', 'high', 'openai', 'high'),
                                                     ('employee', None, 'openai', 'high')]:
                with self.subTest(policy=policy):
                    queued.clear()
                    res = self.client.put('/api/v1/admin/ai-provider', json={'policy': policy, 'level': level})
                    self.assertEqual(res.status_code, 200)
                    res = self.client.post(route, json={'expectedPolicy': policy, 'expectedLevel': level})
                    self.assertEqual(res.json()['started'], len(employees))
                    changed = ('openai', 'low') if policy != 'employee' else ('ollama', None)
                    res = self.client.put('/api/v1/admin/ai-provider', json={'policy': changed[0], 'level': changed[1]})
                    self.assertEqual(res.status_code, 200)
                    descriptor = json.loads(json.dumps(queued[-1]._resume))
                    job_recovery.invoke(descriptor, employees[-1]['employee_id'])
                    chat.reset_mock()
                    for work in queued:
                        work(SimpleNamespace(job_id='job'))
                    self.assertEqual(len(chat.call_args_list), 10)
                    for call in chat.call_args_list:
                        self.assertEqual((call.args[0], call.kwargs['reasoning']), (expected, effort))

    def test_bulk_override_cannot_bypass_managed_mode(self):
        self.save('ollama')
        with patch.object(admin.db, 'all_') as employees:
            response = self.client.post('/api/v1/admin/goal-suggestions/regenerate-all', json={'mode': 'openai'})
        self.assertEqual(response.status_code, 409)
        employees.assert_not_called()

    def test_managed_reasoning_reaches_goals_and_blocks_stale_or_invalid_choices(self):
        from types import SimpleNamespace
        from app.services import goals

        def set_level(policy, level):
            return self.client.put('/api/v1/admin/ai-provider', json={'policy': policy, 'level': level})

        self.assertEqual(set_level('openai', 'high').json()['level'], 'high')
        self.assertEqual(set_level('employee', 'low').status_code, 422)
        self.assertEqual(set_level('openai', 'unsupported').status_code, 422)
        self.assertEqual(provider_policy.selection(), ('openai', 'high'))
        with patch.object(admin.db, 'all_') as rows:
            result = self.client.post('/api/v1/admin/goal-suggestions/regenerate-all',
                                      json={'expectedPolicy': 'openai', 'expectedLevel': 'low'})
            self.assertEqual(result.status_code, 409)
            rows.assert_not_called()
        with patch.object(goals.profile, 'view', return_value={'job': 'engineer'}), patch.object(goals.jobs, 'start') as start:
            goals._request(7, 'admin-pick', None, 'openai', approved_model=goals.bulk_model({}, 'openai', 'high'))
            worker = start.call_args.args[3]
            with patch.object(goals.G, 'run', return_value={'candidates': []}) as generate, patch.object(goals.db, 'tx'):
                worker(SimpleNamespace(job_id='test-job'))
                self.assertEqual(generate.call_args.args[0].reasoning, {'openai': 'high'})
        # RunPod-Ollama 는 추론 없이만 부르므로 단계를 고정할 수 없고, 예전에 저장된 단계도 읽지 않는다
        for stale in ('high', 'on', 'off'):
            with self.subTest(stale=stale):
                self.assertEqual(set_level('ollama', stale).status_code, 422)
        self.assertEqual(provider_policy.selection(), ('openai', 'high'))
        self.assertEqual(set_level('ollama', None).status_code, 200)
        self.assertEqual(runtime.context(1, {}).reasoning, {})
        Path(self.directory, 'ai-provider').write_text('ollama\non\n')
        self.assertEqual(provider_policy.selection(), ('ollama', None))
        self.assertEqual(runtime.context(1, {}).reasoning, {})
        self.assertEqual(self.client.get('/api/v1/admin/ai-provider').json()['level'], None)
        self.assertEqual(goals.bulk_model({}, 'ollama', 'on')['level'], None)
        self.assertEqual(set_level('employee', None).status_code, 200)
        self.assertEqual(goals.bulk_model({'ai_provider': 'ollama', 'reasoning': {'ollama': 'high'}}, None, None),
                         {'provider': 'ollama', 'model': llm.model_name('ollama'), 'level': None, 'default_level': 'off'})
        self.identity.return_value = auth.Account('employee', 1, 'test')
        self.assertEqual(self.client.put('/api/v1/me/reasoning', json={'provider': 'ollama', 'level': 'on'}).status_code, 422)
        ollama = next(p for p in self.client.get('/api/v1/ai/providers').json()['providers'] if p['id'] == 'ollama')
        self.assertEqual(ollama['reasoning'], {'levels': [], 'default': 'off'})

    def test_post_beta_disables_personal_selection(self):
        endpoint = '/api/v1/admin/ai-provider'
        self.assertEqual(provider_policy.current(), 'employee')
        settings = replace(self.settings, employee_ai_selection=False)
        with patch.object(provider_policy, 'S', settings), patch.object(admin, 'S', settings):
            for raw in (None, 'employee\n'):
                with self.subTest(raw=raw):
                    if raw:
                        Path(self.directory, 'ai-provider').write_text(raw)
                    state = self.client.get(endpoint).json()
                    self.assertEqual((state['policy'], state['policyStatus']), ('ollama', 'default_ollama'))
                    self.assertFalse(state['employeeSelectionAllowed'])
            self.assertEqual(self.save('ollama').json()['policyStatus'], 'active')
            self.assertEqual(self.save('employee').status_code, 409)
            self.assertEqual(self.save('openai').status_code, 200)
            self.assertEqual(runtime.context(1, {}).provider, 'openai')

    def test_switch_changes_wire_provider_key_model_and_preserves_started_context(self):
        calls = []
        efforts = []

        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                efforts.append(payload.get('reasoning_effort') if self.path.startswith('/v1/') else payload.get('think'))
                calls.append((self.path, self.headers['Authorization'], payload['model']))
                message = {'content': '{"ok":true}'}
                response = {'choices': [{'message': message}]} if self.path.startswith('/v1/') else {'message': message}
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())

        with ThreadingHTTPServer(('127.0.0.1', 0), Provider) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f'http://127.0.0.1:{server.server_port}'
            try:
                with patch.object(llm, 'S', replace(self.settings, openai_base=url+'/v1', ollama_url=url)):
                    result = self.client.put('/api/v1/admin/ai-provider', json={'policy': 'openai', 'level': 'high'})
                    self.assertEqual(result.status_code, 200)
                    started = runtime.context(1, {})
                    self.assertEqual(self.save('ollama').status_code, 200)
                    for ctx in (started, runtime.context(1, {})):
                        self.assertEqual(runtime.llm_json(ctx, 'Return JSON.', {}, role='regulation'), {'ok': True})
                    for provider in ('ollama', 'openai'):
                        endpoint = f'/api/v1/admin/ai-provider/{provider}/key'
                        self.assertEqual(self.client.put(endpoint, json={'key': 'rotated-' + provider}).status_code, 200)
                        with self.subTest(provider=provider):
                            self.save(provider)
                            runtime.llm_json(runtime.context(1, {}), 'Return JSON.', {}, role='regulation')
                            self.assertEqual(self.client.delete(endpoint).status_code, 200)
                            runtime.llm_json(runtime.context(1, {}), 'Return JSON.', {}, role='regulation')
                    self.assertEqual(self.save('employee').status_code, 200)
                    self.assertEqual(runtime.context(1, {}).provider, 'ollama')
            finally:
                server.shutdown()
                thread.join()
        self.assertEqual(efforts[:2], ['high', False])
        self.assertEqual(calls, [
            ('/v1/chat/completions', 'Bearer example-openai', self.settings.openai_model),
            ('/api/chat', 'Bearer example-ollama', self.settings.ollama_model_regulation),
            ('/api/chat', 'Bearer rotated-ollama', self.settings.ollama_model_regulation),
            ('/api/chat', 'Bearer example-ollama', self.settings.ollama_model_regulation),
            ('/v1/chat/completions', 'Bearer rotated-openai', self.settings.openai_model),
            ('/v1/chat/completions', 'Bearer example-openai', self.settings.openai_model),
        ])
