"""시연 API 공개 범위와 비밀번호 비노출 계약."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')
from dataclasses import replace
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import account
from app.errors import ApiError, api_error_handler
from app import config, llm
from app.admin_io import hr


class DemoAccessTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(account.r)
        app.add_exception_handler(ApiError, api_error_handler)
        self.client = TestClient(app)

    def test_disabled_routes_are_404_before_auth_or_database(self):
        with patch.object(account, 'S', replace(account.S, demo_mode=False)), patch.object(account.profile, 'accounts') as query:
            for method, path in [('get', '/demo/accounts'), ('post', '/demo/reset'), ('post', '/demo/jump'), ('put', '/me/demo-settings')]:
                with self.subTest(path=path):
                    self.assertEqual(self.client.request(method, '/api/v1'+path).status_code, 404)
            query.assert_not_called()

    def test_enabled_accounts_never_return_password(self):
        with patch.object(account, 'S', replace(account.S, demo_mode=True, demo_password='SECRET_SENTINEL')), patch.object(account.profile, 'accounts', return_value=[{'code': '123'}]):
            response = self.client.get('/api/v1/demo/accounts')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['accounts'], [{'code': '123'}])
            self.assertNotIn('demoPassword', response.json())
            self.assertNotIn('SECRET_SENTINEL', response.text)

    def test_demo_default_and_explicit_off(self):
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
