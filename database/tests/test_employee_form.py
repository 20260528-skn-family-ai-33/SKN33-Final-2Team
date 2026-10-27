"""Form validation plus opt-in tests restricted to an isolated review database."""
from copy import deepcopy
from contextlib import redirect_stdout
from datetime import date
from decimal import Decimal
from io import StringIO
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from src.database.employee_form import (
    validate_form_payload, validate_preferences, profile_from_form_fields,
    save_employee_input_form, get_employee_input_form, record_from_form_fields,
)
from src.database.db_client import DatabaseClient


class EmployeeFormValidationTests(unittest.TestCase):
    def test_sheet_labels_keep_multiline_text_and_zero(self):
        original = {'경험 요약': '경험\n요약', '개발 경험 연수': 0,
                    '기술별 사용 경험': 'Python / 1년 / API\nSQL / 2년 / 조회',
                    '프로젝트 경험': '과거 프로젝트 / 역할 / 결과', '교육 이력': '과정 / 기관 / 기간',
                    '목표 상태': '정함', '목표 내용': '규정 검색 구현', '학습 예산': 0,
                    '전달 메모': '검토 요청', '본인 업무 설명': '별도 기존 직원 컬럼'}
        result = profile_from_form_fields(original)
        self.assertEqual(result['development_years'], Decimal(0))
        self.assertEqual(result['technology_experience'], original['기술별 사용 경험'])
        self.assertEqual(result['learning_preferences']['budget_won'], 0)
        self.assertEqual(result['submission_note'], '검토 요청')
        self.assertNotIn('planned_project_description', result)

    def test_blank_sheet_cells_preserve_values(self):
        self.assertEqual(profile_from_form_fields({'경험 요약': '', '개발 경험 연수': None}), {})
        self.assertEqual(profile_from_form_fields({'경험 요약': '   ', '개발 경험 연수': '  '}), {})

    def test_assignment_bigint_ids_match_db_types(self):
        fields = validate_form_payload({'employee': {'department_id': 2147483648, 'job_grade_id': '2147483649'}})['employee']
        self.assertEqual(fields['department_id'], 2147483648)
        self.assertEqual(fields['job_grade_id'], 2147483649)
        with self.assertRaises(ValueError):validate_form_payload({'employee': {'department_id': 9223372036854775808}})

    def test_unknown_or_privileged_fields_are_rejected(self):
        for payload in ({'employee': {'password_hash': 'forbidden'}}, {'employee': {'source_type': 'REAL_USER'}},
                        {'profile': {'employee_id': 1}}, {'employee_work_context': {}},
                        {'profile': {'learning_preferences': {'unknown': 1}}}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_form_payload(payload)

    def test_bad_years_never_round_or_coerce(self):
        for value in (True, -1, 'NaN', 'Infinity', '1.234', '10000', 'not a number'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_form_payload({'profile': {'development_years': value}})

    def test_date_validation(self):
        for value in ('2026-02-30', '20261025', 123, '2026-1-01'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_form_payload({'employee': {'hire_date': value}})
        self.assertEqual(validate_form_payload({'employee': {'hire_date': '2020-01-02'}})['employee']['hire_date'], date(2020, 1, 2))

    def test_typed_flags_ids_and_nullable_job(self):
        self.assertIsNone(validate_form_payload({'employee': {'job_id': None}})['employee']['job_id'])
        for value in (1, 'true', None):
            with self.assertRaises(ValueError):validate_form_payload({'employee': {'is_department_head': value}})
        for values in ([1, 1], [True], [0], None):
            with self.assertRaises(ValueError):validate_form_payload({'skill_ids': values})

    def test_conditional_goals_and_credential_plan(self):
        for preferences in ({'goal_status': '정함'}, {'credential_plan': '구체적 계획'}):
            with self.assertRaises(ValueError):validate_preferences(preferences, complete=True)
        self.assertEqual(validate_preferences({'budget_won': 0})['budget_won'], 0)
        self.assertEqual(validate_preferences(None), {})

    def test_original_payload_is_not_mutated(self):
        original = {'employee': {'hire_date': '2020-01-01'}, 'profile': {'development_years': '2.50'}}
        saved = deepcopy(original)
        validate_form_payload(original)
        self.assertEqual(saved, original)

    def test_invalid_education_and_text(self):
        for payload in ({'education': {'school_name': '학교'}},
                        {'education': {'education_record_id': 'invalid'}},
                        {'profile': {'experience_summary': ['not text']}},
                        {'profile': {'experience_summary': 'bad\x00text'}}):
            with self.assertRaises(ValueError):validate_form_payload(payload)

    def test_full_form_adapter_reuses_existing_tables(self):
        record = record_from_form_fields(
            {'보유 기술 1 ★': '없음', '보유 자격 1 ★': '없음', '직무 ★': '해당 없음',
             '개발 경험 연수': 0, '경험 요약': '원문', '목표 상태': '미정'},
            {'employees.employee_id': 12345, 'employees.name': '가상 예시',
             'employees.hire_date': '2020-01-01', 'employees.is_degree_seeker': 'FALSE',
             'employees.unlisted_certifications': '목록 밖 자격 원문',
             'employees.planned_project_description': '업무와 프로젝트 설명',
             'employee_education_records.school_name': '예시 학교',
             'employee_education_records.education_level': 'bachelor',
             'employee_education_records.enrollment_date': '2015-03-01'})
        self.assertEqual(record['employee_id'], 12345)
        self.assertEqual(record['skill_ids'], [])
        self.assertEqual(record['certification_ids'], [])
        self.assertIsNone(record['employee']['job_id'])
        self.assertFalse(record['employee']['is_degree_seeker'])
        self.assertEqual(record['education']['enrollment_date'], date(2015, 3, 1))
        self.assertEqual(record['profile']['development_years'], Decimal(0))

    def test_cli_private_connection_file_takes_precedence(self):
        path = Path(__file__).resolve().parents[1]/'scripts/employee_form.py'
        spec = importlib.util.spec_from_file_location('form_cli_private', path)
        cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/'form.json').write_text('[{"employee_id":12345,"profile":{"development_years":0}}]', encoding='utf-8')
            (folder/'connection.env').write_text("FORM_DB='postgresql://fake:fake@127.0.0.1:55434/fake_test'\n", encoding='utf-8')
            with patch.object(cli.psycopg, 'connect') as connect, patch.object(cli, 'connect') as legacy, \
                 patch.object(cli, 'import_forms', return_value={'status':'PREVIEW_ROLLED_BACK'}) as importer, redirect_stdout(StringIO()):
                result = cli.main(['--input',str(folder/'form.json'),'--connection-file',str(folder/'connection.env'),'--db-env','FORM_DB'])
            self.assertEqual(result, 0)
            self.assertEqual(connect.call_args.args[0], 'postgresql://fake:fake@127.0.0.1:55434/fake_test')
            self.assertFalse(importer.call_args.kwargs['apply'])
            legacy.assert_not_called()

    def test_cli_missing_private_key_fails_before_connect(self):
        path = Path(__file__).resolve().parents[1]/'scripts/employee_form.py'
        spec = importlib.util.spec_from_file_location('form_cli_missing_key', path)
        cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/'form.json').write_text('[]', encoding='utf-8')
            (folder/'connection.env').write_text('OTHER_KEY=fake', encoding='utf-8')
            output = StringIO()
            with patch.object(cli.psycopg, 'connect') as connect, redirect_stdout(output):
                result = cli.main(['--input',str(folder/'form.json'),'--connection-file',str(folder/'connection.env')])
            self.assertEqual(result, 2)
            self.assertEqual(json.loads(output.getvalue())['status'], 'FAILED')
            connect.assert_not_called()


class EmployeeFormDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv('EMPLOYEE_FORM_TEST_DB_URL')
        if not cls.url:
            raise unittest.SkipTest('Set EMPLOYEE_FORM_TEST_DB_URL for isolated integration tests')
        params = conninfo_to_dict(cls.url)
        if params.get('host') not in ('127.0.0.1', 'localhost', '::1') or not params.get('dbname', '').startswith('growpath_employee_form_test_'):
            raise RuntimeError('Refusing integration tests against a non-review database')

    def setUp(self):
        self.conn = psycopg.connect(self.url, row_factory=dict_row)
        self.conn.execute('SELECT 1')
        self.employee = self.conn.execute("INSERT INTO public.employees(name,email,employee_number,source_type) VALUES('폼 검증 직원',%s,%s,'TEST_MANUAL') RETURNING employee_id", (str(uuid4())+'@growpath.example.invalid','FORM-'+str(uuid4()))).fetchone()['employee_id']
        self.other = self.conn.execute("INSERT INTO public.employees(name,email,employee_number,source_type) VALUES('다른 검증 직원',%s,%s,'TEST_MANUAL') RETURNING employee_id", (str(uuid4())+'@growpath.example.invalid','FORM-'+str(uuid4()))).fetchone()['employee_id']
        self.skills = [r['skill_id'] for r in self.conn.execute('SELECT skill_id FROM public.skill_tags ORDER BY skill_id LIMIT 2').fetchall()]
        self.cert = self.conn.execute('SELECT cert_id FROM public.certifications ORDER BY cert_id LIMIT 1').fetchone()['cert_id']

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def payload(self):
        return {'employee': {'hire_date': '2020-01-01', 'department_start_date': '2021-01-01',
                             'unlisted_certifications': '목록 밖 자격 / 기관 미입력 / 취득일 미입력',
                             'planned_project_description': '현재 업무와 만들고 싶은 검색 프로젝트'},
                'skill_ids': self.skills, 'certification_ids': [self.cert],
                'education': {'school_name': '가상 검증 대학교', 'education_level': 'bachelor',
                              'department_name': '컴퓨터공학', 'enrollment_date': '2015-03-01', 'graduation_date': '2019-02-28'},
                'profile': {'experience_summary': '업무 경험\n배우려는 이유', 'development_years': 0,
                            'technology_experience': 'Python / 0년 / 학습 중\nSQL / 1년 / 조회',
                            'project_experience': '프로젝트 / 기간 / 역할 / 결과',
                            'learning_history': '교육 / 기관 / 기간 / 수강 중 / 80시간',
                            'learning_preferences': {'goal_status': '정함', 'goal_text': '검색 시제품 구현',
                                                     'deliverable': '시연 화면', 'credential_plan': '구체적 계획',
                                                     'desired_credential': '목록 밖 희망 자격', 'budget_won': 0},
                            'submission_note': '폼 전체 항목 검증'}}

    def test_complete_form_roundtrip_and_no_password(self):
        data = self.payload()
        saved = save_employee_input_form(self.conn, self.employee, data)
        self.assertEqual(saved['employee']['hire_date'], date(2020, 1, 1))
        self.assertEqual(saved['employee']['planned_project_description'], data['employee']['planned_project_description'])
        self.assertEqual(saved['skill_ids'], self.skills)
        self.assertEqual(saved['certification_ids'], [self.cert])
        self.assertEqual(saved['education_records'][0]['graduation_date'], date(2019, 2, 28))
        for key in ('experience_summary', 'technology_experience', 'project_experience', 'learning_history', 'submission_note'):
            self.assertEqual(saved['profile'][key], data['profile'][key])
        self.assertEqual(saved['profile']['development_years'], Decimal(0))
        self.assertEqual(saved['profile']['learning_preferences']['budget_won'], 0)
        self.assertNotIn('password_hash', saved['employee'])

    def test_repeat_import_preserves_education_identity(self):
        first = save_employee_input_form(self.conn, self.employee, self.payload())
        again = save_employee_input_form(self.conn, self.employee, self.payload())
        self.assertEqual(len(again['education_records']), 1)
        self.assertEqual(first['education_records'][0]['education_record_id'], again['education_records'][0]['education_record_id'])

    def test_patch_and_explicit_clear(self):
        save_employee_input_form(self.conn, self.employee, self.payload())
        patched = save_employee_input_form(self.conn, self.employee, {'profile': {'experience_summary': None, 'learning_preferences': {'weekly_hours': 4}}})
        self.assertIsNone(patched['profile']['experience_summary'])
        self.assertEqual(patched['skill_ids'], self.skills)
        self.assertEqual(patched['profile']['learning_preferences']['goal_text'], '검색 시제품 구현')
        cleared = save_employee_input_form(self.conn, self.employee, {'skill_ids': [], 'profile': {'learning_preferences': None}})
        self.assertEqual(cleared['skill_ids'], [])
        self.assertEqual(cleared['profile']['learning_preferences'], {})
        self.assertEqual(cleared['certification_ids'], [self.cert])

    def test_foreign_key_failure_rolls_back_the_whole_form(self):
        save_employee_input_form(self.conn, self.employee, self.payload())
        with self.assertRaises(psycopg.IntegrityError):
            save_employee_input_form(self.conn, self.employee, {'employee': {'name': '롤백돼야 하는 이름'}, 'skill_ids': [2147483647], 'profile': {'submission_note': '롤백'}})
        current = get_employee_input_form(self.conn, self.employee)
        self.assertEqual(current['employee']['name'], '폼 검증 직원')
        self.assertEqual(current['skill_ids'], self.skills)
        self.assertEqual(current['profile']['submission_note'], '폼 전체 항목 검증')

    def test_invalid_date_order_is_rejected_without_partial_save(self):
        with self.assertRaises(psycopg.IntegrityError):
            save_employee_input_form(self.conn, self.employee, {'employee': {'hire_date': '2021-01-01', 'department_start_date': '2020-01-01'}, 'profile': {'submission_note': '롤백'}})
        current = get_employee_input_form(self.conn, self.employee)
        self.assertIsNone(current['employee']['hire_date'])
        self.assertEqual(current['profile'], {})

    def test_education_date_order_rolls_back_employee_changes(self):
        data = self.payload()
        data['employee']['name'] = '롤백할 변경'
        data['education']['graduation_date'] = '2010-01-01'
        with self.assertRaises(psycopg.IntegrityError):
            save_employee_input_form(self.conn, self.employee, data)
        current = get_employee_input_form(self.conn, self.employee)
        self.assertEqual(current['employee']['name'], '폼 검증 직원')
        self.assertEqual(current['education_records'], [])

    def test_education_ownership(self):
        other = save_employee_input_form(self.conn, self.other, {'education': self.payload()['education']})
        with self.assertRaises(ValueError):
            save_employee_input_form(self.conn, self.employee, {'employee': {'name': '롤백'}, 'education': {'education_record_id': str(other['education_records'][0]['education_record_id']), 'department_name': '무단 변경'}})
        self.assertEqual(get_employee_input_form(self.conn, self.employee)['employee']['name'], '폼 검증 직원')

    def test_self_service_access_and_assignment_separation(self):
        db = DatabaseClient(self.conn)
        with self.assertRaises(ValueError):db.get_employee_input_form(self.employee, actor_employee_id=self.other)
        with self.assertRaises(ValueError):db.save_employee_input_profile(self.employee, {'experience_summary': '금지'}, actor_employee_id=self.other)
        with self.assertRaises(ValueError):db.save_employee_input_profile(self.employee, {'institution_id': '금지'}, actor_employee_id=self.employee)
        saved = db.save_employee_input_profile(self.employee, {'development_years': 0}, actor_employee_id=self.employee)
        self.assertEqual(saved['profile']['development_years'], '0.00')
        self.assertTrue(db.table('employee_input_profiles').select('employee_id').eq('employee_id', self.employee).execute().data)

    def test_rls_and_direct_json_shape_guard(self):
        row = self.conn.execute("SELECT relrowsecurity FROM pg_class WHERE oid='public.employee_input_profiles'::regclass").fetchone()
        self.assertTrue(row['relrowsecurity'])
        with self.assertRaises(psycopg.IntegrityError), self.conn.transaction():
            self.conn.execute("INSERT INTO public.employee_input_profiles(employee_id,learning_preferences) VALUES(%s,'[]'::jsonb)", (self.employee,))

    def test_default_operator_preview_does_not_persist(self):
        path = Path(__file__).resolve().parents[1]/'scripts/employee_form.py'
        spec = importlib.util.spec_from_file_location('form_import_cli', path)
        cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
        result = cli.import_forms(self.conn, [{'employee_id': self.employee, **self.payload()}])
        self.assertEqual(result['status'], 'PREVIEW_ROLLED_BACK')
        self.assertEqual(get_employee_input_form(self.conn, self.employee)['profile'], {})
        self.assertEqual(get_employee_input_form(self.conn, self.employee)['education_records'], [])

    def test_batch_failure_keeps_other_employees_unchanged(self):
        path = Path(__file__).resolve().parents[1]/'scripts/employee_form.py'
        spec = importlib.util.spec_from_file_location('form_import_batch_cli', path)
        cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
        with self.assertRaises(psycopg.IntegrityError):
            cli.import_forms(self.conn, [{'employee_id': self.employee, **self.payload()},
                                       {'employee_id': self.other, 'skill_ids': [2147483647]}], apply=True)
        self.assertEqual(get_employee_input_form(self.conn, self.employee)['profile'], {})


if __name__ == '__main__':
    unittest.main()
