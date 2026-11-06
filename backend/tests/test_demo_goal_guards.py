"""시연 비활성 모드에서 명시적 가데이터 요청의 저장·작업 등록을 차단한다."""
import os
from dataclasses import replace
import unittest
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import admin_io, auth
from app.errors import ApiError, api_error_handler
from app.routers import admin
from app.services import goals
from tools import setup_db


class DemoGoalGuardTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(admin.r)
        app.add_exception_handler(ApiError, api_error_handler)
        self.client = TestClient(app)

    def test_disabled_service_paths_reject_before_database_or_jobs(self):
        calls = (
            lambda: goals.request(1, 'admin-all', mode='mock'),
            lambda: goals._request(1, 'resume', None, 'mock'),
            goals.seed_all,
            lambda: admin_io.edit('hr', 1, [], True, 'token', 'mock'),
            lambda: admin_io.apply('test-upload', 1, 'mock'),
        )
        with patch.object(goals, 'S', replace(goals.S, demo_mode=False)), \
             patch.object(goals.db, 'tx') as transaction, patch.object(goals.db, 'one') as one, \
             patch.object(goals.db, 'all_') as rows, patch.object(goals.jobs, 'start') as start, \
             patch.object(goals.profile, 'view') as profile, patch.object(goals.G, 'run') as model:
            for call in calls:
                with self.subTest(call=call), self.assertRaises(ApiError) as error:
                    call()
                self.assertEqual(error.exception.status, 409)
                self.assertEqual(error.exception.code, 'DEMO_DISABLED')
            for mocked in (transaction, one, rows, start, profile, model):
                mocked.assert_not_called()

    def test_disabled_admin_mock_requests_fail_before_query_or_save(self):
        requests = (
            ('/goal-suggestions/regenerate-all', {'mode': 'mock'}),
            ('/datasets/hr/edit', {'goalMode': 'mock', 'rows': [], 'save': True}),
            ('/uploads/test-upload/apply', {'goalMode': 'mock'}),
        )
        with patch.object(goals, 'S', replace(goals.S, demo_mode=False)), \
             patch.object(auth, 'account_of', return_value=auth.Account('admin', 1, 'test')), \
             patch.object(goals.db, 'tx') as transaction, patch.object(goals.db, 'one') as one, \
             patch.object(goals.db, 'all_') as rows, patch.object(goals.jobs, 'start') as start:
            for path, body in requests:
                with self.subTest(path=path):
                    response = self.client.post('/api/v1/admin' + path, json=body)
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.json()['error']['code'], 'DEMO_DISABLED')
            for mocked in (transaction, one, rows, start):
                mocked.assert_not_called()

    def test_bulk_mock_keeps_admin_permission_checks(self):
        with patch.object(goals, 'S', replace(goals.S, demo_mode=True)), \
             patch.object(goals.db, 'all_') as rows:
            self.assertEqual(self.client.post('/api/v1/admin/goal-suggestions/regenerate-all', json={'mode': 'mock'}).status_code, 401)
            with patch.object(auth, 'account_of', return_value=auth.Account('employee', 1, 'test')):
                response = self.client.post('/api/v1/admin/goal-suggestions/regenerate-all', json={'mode': 'mock'})
                self.assertEqual(response.status_code, 403)
            rows.assert_not_called()

    def test_enabled_bulk_mock_keeps_explicit_mode(self):
        with patch.object(goals, 'S', replace(goals.S, demo_mode=True)), \
             patch.object(auth, 'account_of', return_value=auth.Account('admin', 1, 'test')), \
             patch.object(goals.db, 'all_', return_value=[{'employee_id': 7}]), \
             patch.object(goals, 'request', return_value='job') as request:
            response = self.client.post('/api/v1/admin/goal-suggestions/regenerate-all', json={'mode': 'mock'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['mode'], 'mock')
            request.assert_called_once_with(7, 'admin-all', mode='mock')

    def test_allowed_modes_are_not_rewritten(self):
        for enabled in (False, True):
            modes = (None, 'openai', 'ollama', 'mock') if enabled else (None, 'openai', 'ollama')
            for mode in modes:
                with self.subTest(enabled=enabled, mode=mode), \
                     patch.object(goals, 'S', replace(goals.S, demo_mode=enabled)), \
                     patch.object(goals.db, 'tx') as transaction, \
                     patch.object(goals, '_request', return_value='job') as request:
                    transaction.return_value.__enter__.return_value.one.return_value = {}
                    self.assertEqual(goals.request(1, 'manual', mode=mode), 'job')
                    request.assert_called_once_with(1, 'manual', None, mode)

    def test_enabled_seed_retains_existing_empty_database_behavior(self):
        with patch.object(goals, 'S', replace(goals.S, demo_mode=True)), \
             patch.object(goals.db, 'all_', return_value=[]) as rows:
            self.assertEqual(goals.seed_all(), 0)
            rows.assert_called_once()

    def test_offline_setup_skips_seeding_without_selecting_a_live_provider(self):
        with patch.object(setup_db, 'S', replace(setup_db.S, demo_mode=False)), \
             patch.object(goals, 'seed_all') as seed, patch.object(goals, 'request') as request, \
             patch.object(setup_db, 'say') as say:
            setup_db.goals()
            seed.assert_not_called()
            request.assert_not_called()
            self.assertIn('GP5_DEMO_MODE=off', say.call_args.args[0])
