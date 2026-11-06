"""설치기의 직원 비밀번호 보존과 신규 계정 초기값: 실제 DB 대신 모의 트랜잭션을 사용한다."""
import os
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from io import StringIO
import unittest
from unittest.mock import MagicMock, call, patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app import config
from app.admin_io import hr
from app.admin_io.base import Row
from app.errors import ApiError
from tools import setup_db


class SetupPasswordTests(unittest.TestCase):
    def setUp(self):
        self.transaction = MagicMock()
        self.transaction.one.return_value = None
        self.db_context = patch.object(setup_db.db, 'tx')
        self.db_tx = self.db_context.start()
        self.db_tx.return_value.__enter__.return_value = self.transaction
        self.addCleanup(self.db_context.stop)
        self.hasher = patch.object(setup_db, 'hash_password', return_value='ADMIN_HASH')
        self.hash_password = self.hasher.start()
        self.addCleanup(self.hasher.stop)
        self.messages = patch.object(setup_db, 'say')
        self.messages.start()
        self.addCleanup(self.messages.stop)

    @contextmanager
    def isolated_setup_steps(self):
        """읽기 전용 진입점이 계정·자료 보충 함수를 호출하지 않는지 검사한다."""
        with ExitStack() as stack:
            steps = {name: stack.enter_context(patch.object(setup_db, name)) for name in (
                'admin_account', 'team_passwords', 'resources', 'regulations', 'goals',
            )}
            stack.enter_context(patch('builtins.print'))
            yield steps

    def test_setup_preserves_passwords_and_skips_supplements_in_both_demo_modes(self):
        for enabled in (False, True):
            for password in ('', '   ', 'employee-test', 'changed-test'):
                with self.subTest(demo_mode=enabled, password_case=password), \
                     patch.object(setup_db, 'S', replace(
                         setup_db.S, demo_mode=enabled, demo_password=password,
                     )), self.isolated_setup_steps() as steps, \
                     patch('tools.verify_bge_database.verify', return_value={'vectors': 4832}) as verify:
                    setup_db.main([])
                    setup_db.main([])
                    self.assertEqual(verify.call_count, 2)
                    for step in steps.values():
                        step.assert_not_called()
        self.db_tx.assert_not_called()
        self.hash_password.assert_not_called()

    def test_setup_rejects_legacy_options_before_verifying_or_writing_database(self):
        options = (['--reset-team-passwords'], ['--keep-team-passwords'],
                   ['--supplement-only'], ['--reset-team-passwords', '--keep-team-passwords'],
                   ['--reset-team-passwords', '--supplement-only'])
        for args in options:
            with self.subTest(args=args), self.isolated_setup_steps() as steps, \
                 patch('tools.verify_bge_database.verify') as verify, \
                 patch('sys.stderr', new_callable=StringIO) as errors:
                with self.assertRaises(SystemExit) as failure:
                    setup_db.main(args)
                self.assertEqual(failure.exception.code, 2)
                self.assertIn(args[0], errors.getvalue())
                verify.assert_not_called()
                for step in steps.values():
                    step.assert_not_called()
        self.db_tx.assert_not_called()
        self.hash_password.assert_not_called()

    def test_team_passwords_rejects_direct_blank_call_before_database_access(self):
        for password in ('', '   ', '\t\r\n'):
            with self.subTest(password_case=repr(password)), \
                 patch.object(setup_db, 'S', replace(setup_db.S, demo_password=password)):
                with self.assertRaisesRegex(ValueError, 'GP5_DEMO_PASSWORD'):
                    setup_db.team_passwords()
        self.db_tx.assert_not_called()
        self.hash_password.assert_not_called()

    def test_team_passwords_resets_only_nonmatching_numbered_employees(self):
        self.transaction.all.return_value = [
            {'employee_id': 11, 'password_hash': 'MATCHING_HASH'},
            {'employee_id': 12, 'password_hash': 'DIFFERENT_HASH'},
            {'employee_id': 13, 'password_hash': None},
        ]
        self.hash_password.return_value = 'NEW_EMPLOYEE_HASH'
        with patch.object(setup_db, 'S', replace(setup_db.S, demo_password=' employee-test ')), \
             patch.object(setup_db, 'verify_password', side_effect=[True, False, False]) as verify:
            setup_db.team_passwords()
        selection = ' '.join(self.transaction.all.call_args.args[0].split())
        self.assertIn('FROM public.employees', selection)
        self.assertIn("coalesce(btrim(employee_number), '') <> ''", selection)
        self.assertEqual(verify.call_args_list, [
            call('MATCHING_HASH', ' employee-test '),
            call('DIFFERENT_HASH', ' employee-test '),
            call(None, ' employee-test '),
        ])
        self.assertEqual(self.hash_password.call_args_list,
                         [call(' employee-test '), call(' employee-test ')])
        self.assertEqual([item.kwargs for item in self.transaction.run.call_args_list], [
            {'h': 'NEW_EMPLOYEE_HASH', 'i': 12}, {'h': 'NEW_EMPLOYEE_HASH', 'i': 13},
        ])
        for update in self.transaction.run.call_args_list:
            self.assertIn('UPDATE public.employees SET password_hash', update.args[0])
            self.assertIn('WHERE employee_id = :i', update.args[0])

    def test_team_passwords_does_not_rehash_matching_passwords_on_repeated_reset(self):
        self.transaction.all.return_value = [{'employee_id': 11, 'password_hash': 'MATCHING_HASH'}]
        with patch.object(setup_db, 'S', replace(setup_db.S, demo_password='employee-test')), \
             patch.object(setup_db, 'verify_password', return_value=True):
            setup_db.team_passwords()
            setup_db.team_passwords()
        self.hash_password.assert_not_called()
        self.transaction.run.assert_not_called()

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
            setup_db.main([])
        verify.assert_called_once_with()
        self.hash_password.assert_not_called()
        self.transaction.run.assert_not_called()

    def test_setup_propagates_invalid_bge_database(self):
        with patch('tools.verify_bge_database.verify', side_effect=ValueError('BGE DB 입력 계약 오류')):
            with self.assertRaisesRegex(ValueError, 'BGE DB'):
                setup_db.main([])
        self.transaction.run.assert_not_called()


class HrPasswordCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.transaction = MagicMock()
        self.transaction.all.return_value = []
        self.transaction.val.return_value = 11
        current = patch.object(hr, 'current', return_value={})
        current.start()
        self.addCleanup(current.stop)
        institution = patch.object(hr, '_inst', return_value='QA')
        institution.start()
        self.addCleanup(institution.stop)

    def test_new_hr_employee_keeps_independent_initial_password_in_both_demo_modes(self):
        row = Row('직원', 2, {'name': '신규 시험 직원'}, {'name'}, key=('QA11',), action='add')
        for enabled in (False, True):
            with self.subTest(demo_mode=enabled), patch.object(hr, 'S', replace(
                hr.S, demo_mode=enabled, demo_password='employee-test', admin_password='admin-test',
            )), patch.object(hr, 'hash_password', return_value='EMPLOYEE_HASH') as hasher:
                self.transaction.reset_mock()
                result = hr.apply(self.transaction, {'직원': [row]}, {}, {'source': 'form'})
                hasher.assert_called_once_with('employee-test')
                inserted = [item for item in self.transaction.val.call_args_list
                            if 'INSERT INTO public.employees' in item.args[0]]
                self.assertEqual(len(inserted), 1)
                self.assertEqual(inserted[0].kwargs['pw'], 'EMPLOYEE_HASH')
                self.assertEqual(inserted[0].kwargs['c'], 'QA11')
                self.assertEqual(result['직원']['add'], 1)

    def test_new_hr_employee_without_initial_password_is_rejected(self):
        row = Row('직원', 2, {'name': '신규 시험 직원'}, {'name'}, key=('QA11',), action='add')
        with patch.object(hr, 'S', replace(hr.S, demo_password='', admin_password='admin-test')), \
             patch.object(hr, 'hash_password') as hasher:
            with self.assertRaises(ApiError) as failure:
                hr.apply(self.transaction, {'직원': [row]}, {}, {'source': 'form'})
            self.assertEqual(failure.exception.code, 'NO_DEMO_PASSWORD')
            hasher.assert_not_called()
            self.transaction.val.assert_not_called()
            self.transaction.run.assert_not_called()

    def test_existing_hr_employee_update_does_not_reset_password(self):
        row = Row('직원', 2, {'name': '변경된 이름'}, {'name'}, key=('QA11',), action='update')
        existing = {'직원': {('QA11',): {'_id': 11, 'name': '기존 이름'}}}
        with patch.object(hr, 'S', replace(hr.S, demo_password='changed-employee-test')), \
             patch.object(hr, 'hash_password') as hasher:
            result = hr.apply(self.transaction, {'직원': [row]}, existing, {'source': 'form'})
            hasher.assert_not_called()
        updates = [item for item in self.transaction.run.call_args_list
                   if 'UPDATE public.employees' in item.args[0]]
        self.assertEqual(len(updates), 1)
        self.assertNotIn('password_hash', updates[0].args[0])
        self.assertEqual(updates[0].kwargs['e'], 11)
        self.assertEqual(updates[0].kwargs['n'], '변경된 이름')
        self.assertEqual(result['직원']['update'], 1)


if __name__ == '__main__':
    unittest.main()
