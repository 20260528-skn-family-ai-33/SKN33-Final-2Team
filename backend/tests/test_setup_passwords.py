"""관리자 최초 비밀번호 분리: 실제 DB·계정 대신 모의 트랜잭션을 사용한다."""
import os
from dataclasses import replace
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app import config
from tools import setup_db


class SetupPasswordTests(unittest.TestCase):
    def setUp(self):
        self.transaction = MagicMock()
        self.transaction.one.return_value = None
        self.db_context = patch.object(setup_db.db, 'tx')
        self.db_context.start().return_value.__enter__.return_value = self.transaction
        self.addCleanup(self.db_context.stop)
        self.hasher = patch.object(setup_db, 'hash_password', return_value='ADMIN_HASH')
        self.hash_password = self.hasher.start()
        self.addCleanup(self.hasher.stop)
        self.messages = patch.object(setup_db, 'say')
        self.messages.start()
        self.addCleanup(self.messages.stop)

    def test_config_does_not_fall_back_to_employee_password(self):
        with patch.dict(os.environ, {'GP5_DEMO_PASSWORD': 'employee-test'}, clear=True), patch.object(config, '_FILE', {}):
            settings = config.load()
        self.assertEqual(settings.demo_password, 'employee-test')
        self.assertEqual(settings.admin_password, '')

    def test_config_reads_independent_admin_password(self):
        with patch.dict(os.environ, {'GP5_ADMIN_PASSWORD': 'admin-test'}, clear=True), patch.object(config, '_FILE', {}):
            settings = config.load()
        self.assertEqual(settings.admin_password, 'admin-test')
        self.assertEqual(settings.demo_password, '')

    def test_new_admin_uses_independent_password_in_both_modes(self):
        for enabled in (False, True):
            with self.subTest(demo_mode=enabled), patch.object(setup_db, 'S', replace(
                setup_db.S, demo_mode=enabled, admin_login='test-admin',
                admin_password='admin-test', demo_password='employee-test',
            )):
                self.transaction.reset_mock()
                self.hash_password.reset_mock()
                setup_db.admin_account()
                self.hash_password.assert_called_once_with('admin-test')
                self.transaction.run.assert_called_once()
                query = self.transaction.run.call_args
                self.assertIn('INSERT INTO app_ext.admin_accounts', query.args[0])
                self.assertEqual(query.kwargs['l'], 'test-admin')
                self.assertEqual(query.kwargs['h'], 'ADMIN_HASH')

    def test_existing_admin_is_never_rehashed_or_updated(self):
        self.transaction.one.return_value = {'exists': 1}
        for password in ('', 'employee-test', 'changed-admin-test'):
            with self.subTest(password_case=bool(password)), patch.object(setup_db, 'S', replace(
                setup_db.S, admin_password=password, demo_password='employee-test',
            )):
                setup_db.admin_account()
        self.hash_password.assert_not_called()
        self.transaction.run.assert_not_called()

    def test_new_admin_rejects_empty_password_in_both_modes(self):
        for enabled in (False, True):
            for password in ('', '   '):
                with self.subTest(demo_mode=enabled, blank=not password), patch.object(setup_db, 'S', replace(
                    setup_db.S, demo_mode=enabled, admin_password=password, demo_password='employee-test',
                )):
                    with self.assertRaisesRegex(SystemExit, 'GP5_ADMIN_PASSWORD'):
                        setup_db.admin_account()
        self.hash_password.assert_not_called()
        self.transaction.run.assert_not_called()

    def test_new_admin_rejects_employee_password_in_both_modes(self):
        for enabled in (False, True):
            with self.subTest(demo_mode=enabled), patch.object(setup_db, 'S', replace(
                setup_db.S, demo_mode=enabled, admin_password='shared-test', demo_password='shared-test',
            )):
                with self.assertRaisesRegex(SystemExit, '다른 값') as failure:
                    setup_db.admin_account()
                self.assertNotIn('shared-test', str(failure.exception))
        self.hash_password.assert_not_called()
        self.transaction.run.assert_not_called()

    def test_setup_only_verifies_bge_database_without_writes(self):
        with patch('tools.verify_bge_database.verify', return_value={'vectors': 4832}) as verify, patch('builtins.print'):
            setup_db.main()
        verify.assert_called_once_with()
        self.hash_password.assert_not_called()
        self.transaction.run.assert_not_called()

    def test_setup_propagates_invalid_bge_database(self):
        with patch('tools.verify_bge_database.verify', side_effect=ValueError('BGE DB 입력 계약 오류')):
            with self.assertRaisesRegex(ValueError, 'BGE DB'):
                setup_db.main()
        self.transaction.run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
