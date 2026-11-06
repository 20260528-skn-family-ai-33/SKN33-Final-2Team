"""시연 API 공개 범위와 비밀번호 비노출 계약."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')
from dataclasses import replace
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import account
from app.errors import ApiError, api_error_handler
from app import auth, config, llm
from app.admin_io import hr
from app.agents import runtime as rt


class DemoAccessTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(account.r)
        app.add_exception_handler(ApiError, api_error_handler)
        self.client = TestClient(app)

    def test_disabled_demo_routes_are_404_even_when_account_picker_is_enabled(self):
        with patch.object(account, 'S', replace(account.S, demo_mode=False, beta_account_picker=True)), \
             patch.object(account.profile, 'accounts') as query, \
             patch.object(auth, 'account_of') as authentication, \
             patch.object(rt, 'all_logs') as logs, patch.object(account.db, 'all_') as database:
            for method, path in [('post', '/demo/reset'), ('post', '/demo/jump'), ('put', '/me/demo-settings'), ('get', '/ai/log')]:
                with self.subTest(path=path):
                    self.assertEqual(self.client.request(method, '/api/v1'+path).status_code, 404)
            query.assert_not_called()
            authentication.assert_not_called()
            logs.assert_not_called()
            database.assert_not_called()

    def test_enabled_ai_log_requires_login_and_preserves_authenticated_access(self):
        with patch.object(account, 'S', replace(account.S, demo_mode=True)), \
             patch.object(rt, 'all_logs', return_value=[{'employeeId': 1, 't': 10, 'output': 'test'}]) as logs, \
             patch.object(account.db, 'all_', return_value=[{'employee_id': 1, 'name': '시험 직원'}]):
            self.assertEqual(self.client.get('/api/v1/ai/log').status_code, 401)
            logs.assert_not_called()
            for role in ('employee', 'admin'):
                with self.subTest(role=role), patch.object(auth, 'account_of', return_value=auth.Account(role, 1, 'test')):
                    response = self.client.get('/api/v1/ai/log')
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()['log'], [{'employeeId': 1, 'output': 'test', 'employee': '시험 직원'}])

    def test_providers_reports_demo_mode_to_authenticated_accounts(self):
        self.assertEqual(self.client.get('/api/v1/ai/providers').status_code, 401)
        for enabled in (False, True):
            for role in ('employee', 'admin'):
                with self.subTest(enabled=enabled, role=role), \
                     patch.object(account, 'S', replace(account.S, demo_mode=enabled)), \
                     patch.object(auth, 'account_of', return_value=auth.Account(role, 1, 'test')), \
                     patch.object(account, '_settings', return_value={'aiProvider': 'openai'}):
                    response = self.client.get('/api/v1/ai/providers')
                    self.assertEqual(response.status_code, 200)
                    self.assertIs(response.json()['demoMode'], enabled)

    def test_enabled_accounts_never_return_password(self):
        with patch.object(account, 'S', replace(account.S, demo_mode=False, beta_account_picker=True, demo_password='SECRET_SENTINEL')), patch.object(account.profile, 'accounts', return_value=[{'code': '123'}]):
            response = self.client.get('/api/v1/demo/accounts')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['accounts'], [{'code': '123'}])
            self.assertEqual(set(response.json()), {'accounts', 'adminLogin'})
            self.assertNotIn('demoPassword', response.json())
            self.assertNotIn('SECRET_SENTINEL', response.text)

    def test_account_picker_flag_is_independent_of_demo_mode(self):
        for picker_enabled in (False, True):
            for demo_enabled in (False, True):
                with self.subTest(picker=picker_enabled, demo=demo_enabled), \
                     patch.object(account, 'S', replace(account.S, beta_account_picker=picker_enabled, demo_mode=demo_enabled)), \
                     patch.object(account.profile, 'accounts', return_value=[{'code': 'QA109'}]) as query, \
                     patch.object(account.db, 'all_') as database, patch.object(auth, 'account_of') as authentication:
                    response = self.client.get('/api/v1/demo/accounts')
                    if picker_enabled:
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.json()['accounts'], [{'code': 'QA109'}])
                        query.assert_called_once_with()
                    else:
                        self.assertEqual(response.status_code, 404)
                        self.assertEqual(response.json()['error']['code'], 'NOT_FOUND')
                        query.assert_not_called()
                    database.assert_not_called()
                    authentication.assert_not_called()

    def test_account_picker_defaults_off_and_accepts_explicit_on_off(self):
        with patch.dict(os.environ), patch.dict(config._FILE):
            os.environ.pop('GP5_BETA_ACCOUNT_PICKER', None)
            config._FILE.pop('GP5_BETA_ACCOUNT_PICKER', None)
            self.assertFalse(config.load().beta_account_picker)
        for picker in ('on', 'off'):
            for demo in ('on', 'off'):
                with self.subTest(picker=picker, demo=demo), patch.dict(os.environ, {
                    'GP5_BETA_ACCOUNT_PICKER': picker, 'GP5_DEMO_MODE': demo,
                }):
                    self.assertEqual(config.load().beta_account_picker, picker == 'on')

    def test_demo_default_and_explicit_off(self):
        with patch.dict(os.environ), patch.dict(config._FILE):
            os.environ.pop('GP5_DEMO_MODE', None)
            config._FILE.pop('GP5_DEMO_MODE', None)
            self.assertTrue(config.load().demo_mode)
        with patch.dict(os.environ, {'GP5_DEMO_MODE': 'off'}):
            self.assertFalse(config.load().demo_mode)
        with patch.dict(os.environ, {'GP5_DEMO_MODE': 'on'}):
            self.assertTrue(config.load().demo_mode)

    def test_hr_guide_has_no_password_interpolation(self):
        self.assertIn('관리자에게 받은 초기 비밀번호', '\n'.join(hr.GUIDE))
        self.assertNotIn('GP5_DEMO_PASSWORD', '\n'.join(hr.GUIDE))

    def test_missing_openai_key_is_unavailable(self):
        with patch.object(llm, 'S', replace(llm.S, openai_key='')):
            self.assertFalse(llm.available('openai'))

    def test_saved_demo_options_follow_server_mode_without_changing_storage(self):
        saved = {'ai_provider': 'openai', 'demo_mock': True,
                 'fail_sim': {'goal': True, 'gen': True}, 'reasoning': {'openai': 'low'}}
        original = deepcopy(saved)
        for enabled in (False, True):
            with self.subTest(enabled=enabled), \
                 patch.object(account, 'S', replace(account.S, demo_mode=enabled)), \
                 patch.object(rt, 'S', replace(rt.S, demo_mode=enabled)), \
                 patch.object(account.db, 'one', return_value=saved), \
                 patch.object(account.db, 'tx') as transaction:
                settings = account._settings(1)
                ctx = rt.context(1, {'name': 'test'})
                self.assertEqual(settings['demoMock'], enabled)
                self.assertEqual(ctx.demo, enabled)
                expected_failures = saved['fail_sim'] if enabled else {}
                self.assertEqual(settings['failSim'], expected_failures)
                self.assertEqual(ctx.fail_sim, expected_failures)
                self.assertEqual(settings['aiProvider'], 'openai')
                self.assertEqual(ctx.provider, 'openai')
                self.assertEqual(settings['reasoning'], saved['reasoning'])
                self.assertEqual(ctx.reasoning, saved['reasoning'])
                self.assertEqual(saved, original)
                transaction.assert_not_called()

    def test_missing_settings_keep_demo_disabled_in_both_modes(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), \
                 patch.object(account, 'S', replace(account.S, demo_mode=enabled)), \
                 patch.object(rt, 'S', replace(rt.S, demo_mode=enabled)), \
                 patch.object(account.db, 'one', return_value=None):
                self.assertEqual(account._settings(1), {
                    'aiProvider': 'ollama', 'demoMock': False, 'failSim': {}, 'reasoning': {}})
                ctx = rt.context(1, {})
                self.assertFalse(ctx.demo)
                self.assertEqual(ctx.fail_sim, {})

    def test_disabled_demo_runs_live_callback_without_saved_simulated_failure(self):
        saved = {'ai_provider': 'openai', 'demo_mock': True, 'fail_sim': {'goal': True}}
        mock_fn, live_fn = Mock(), Mock(return_value={'source': 'live-stub'})
        with patch.object(rt, 'S', replace(rt.S, demo_mode=False)), \
             patch.object(rt.db, 'one', return_value=saved), \
             patch.object(rt.llm, 'available', return_value=True), \
             patch.object(rt.llm, 'model_name', return_value='test-model'), \
             patch.object(rt, '_log'):
            ctx = rt.context(1, {})
            sim = rt.sim_once(ctx, 'goal', 'demo-disabled-regression')
            self.assertIsNone(sim)
            self.assertEqual(rt.run(ctx, 'test', 'goal', {}, mock_fn, live_fn, sim=sim),
                             {'source': 'live-stub'})
            live_fn.assert_called_once_with({})
            mock_fn.assert_not_called()

    def test_disabled_demo_does_not_fall_back_when_provider_is_unavailable(self):
        mock_fn, live_fn = Mock(), Mock()
        with patch.object(rt, 'S', replace(rt.S, demo_mode=False)), \
             patch.object(rt.db, 'one', return_value={'demo_mock': True}), \
             patch.object(rt.llm, 'available', return_value=False), \
             patch.object(rt, '_log'):
            ctx = rt.context(1, {})
            with self.assertRaises(rt.AgentError):
                rt.run(ctx, 'test', 'goal', {}, mock_fn, live_fn, mock_delay=0)
            mock_fn.assert_not_called()
            live_fn.assert_not_called()
