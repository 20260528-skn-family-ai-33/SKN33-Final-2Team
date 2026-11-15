"""처음 접속 튜토리얼(#277): /me 의 답함 여부와 답한 시각 기록."""
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import ProgrammingError

from app import auth
from app.errors import ApiError, api_error_handler
from app.routers import account


class TutorialPromptTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(account.r)
        app.add_exception_handler(ApiError, api_error_handler)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.identity = self.enterContext(patch.object(auth, 'account_of', return_value=auth.Account('employee', 7, 'test')))
        self.enterContext(patch.object(account.profile, 'view', return_value={'id': 7}))
        self.enterContext(patch.object(account, '_settings', return_value={'aiProvider': 'ollama'}))

    def me(self, **val):
        with patch.object(account.db, 'val', **val) as read:
            response = self.client.get('/api/v1/me')
        self.assertEqual(response.status_code, 200)
        return response.json(), read

    def test_null_or_missing_row_is_not_answered(self):
        body, read = self.me(return_value=None)
        self.assertIs(body['tutorialAnswered'], False)
        self.assertEqual(read.call_args.kwargs, {'e': 7})

    def test_saved_time_is_answered(self):
        body, _ = self.me(return_value='2026-11-15T09:00:00+09:00')
        self.assertIs(body['tutorialAnswered'], True)

    def test_missing_column_keeps_login_working_without_tutorial(self):
        error = ProgrammingError('SELECT', {}, Exception('column "tutorial_answered_at" does not exist'))
        with self.assertLogs(account.logger, 'WARNING') as logs:
            body, _ = self.me(side_effect=error)
        self.assertIs(body['tutorialAnswered'], True)
        self.assertIn('migrate_tutorial_prompt.sql', logs.output[0])

    def test_admin_response_has_no_tutorial_field(self):
        self.identity.return_value = auth.Account('admin', 1, 'test')
        response = self.client.get('/api/v1/me')
        self.assertNotIn('tutorialAnswered', response.json())

    def test_answer_keeps_the_first_time(self):
        ran = []

        class Tx:
            def run(self, sql, **params):
                ran.append((sql, params))
                return 1

        @contextmanager
        def tx():
            yield Tx()

        with patch.object(account.db, 'tx', tx):
            response = self.client.put('/api/v1/me/tutorial')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'tutorialAnswered': True})
        sql, params = ran[0]
        self.assertEqual(params, {'e': 7})
        self.assertIn('COALESCE(app_ext.user_settings.tutorial_answered_at', sql)

    def test_admin_cannot_answer(self):
        self.identity.return_value = auth.Account('admin', 1, 'test')
        self.assertEqual(self.client.put('/api/v1/me/tutorial').status_code, 403)


if __name__ == '__main__':
    unittest.main()
