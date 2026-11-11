"""HR 양식에 남아 있는 구버전 평정 데이터를 직원 변경으로 해석하지 않는다."""
from datetime import datetime, timezone
import io
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')
from openpyxl import load_workbook

from app import admin_io
from app.admin_io import base, hr
from app.errors import ApiError


class HrSheetsTests(unittest.TestCase):
    def test_template_and_old_workbook(self):
        raw, _, _ = admin_io.export('hr', 'xlsx', empty=True)
        workbook = load_workbook(io.BytesIO(raw))
        self.assertEqual(set(workbook.sheetnames), {'안내', '부서', '직원'})
        workbook.create_sheet('평정').append(['사번', '기간', '평정명'])
        output = io.BytesIO()
        workbook.save(output)
        found, notes = base.read_upload('hr.xlsx', output.getvalue(), hr.SHEETS, None)
        self.assertEqual(set(found), {'직원', '부서'})
        self.assertTrue(any('평정' in n for n in notes))

    def test_partial_retired_headers_are_rejected_but_employee_csv_is_supported(self):
        with patch.object(admin_io, '_compute') as compute:
            for column in ('기간', '등급', '점수', '평정명', '목표 추천 활용 기본 동의'):
                raw = f'사번,이름,{column},삭제\n123,예시,A,Y'.encode()
                for hint in (None, '직원', '부서'):
                    with self.subTest(column=column, hint=hint), self.assertRaises(ApiError) as caught:
                        admin_io.preview('hr', 1, 'old.csv', raw, hint)
                    self.assertEqual(caught.exception.code, 'NO_SHEET')
            compute.assert_not_called()
        found, _ = base.read_upload('hr.csv', '사번,이름,직급\n123,예시,대리'.encode(), hr.SHEETS, None,
                                    retired_csv_headers=hr.RETIRED_CSV_HEADERS)
        self.assertEqual(found['직원'][0].values['grade'], '대리')

    def test_unapplied_hr_csv_from_previous_version_requires_new_preview(self):
        old = {'dataset': 'hr', 'file_name': 'hr.csv', 'status': 'previewed',
               'created_at': datetime.now(timezone.utc), 'plan': {}}
        with patch.object(admin_io.db, 'one', return_value=old), patch.object(admin_io.db, 'tx') as tx:
            with self.assertRaises(ApiError) as caught:
                admin_io.apply('00000000-0000-0000-0000-000000000001', 1)
            self.assertEqual(caught.exception.code, 'STALE_PREVIEW')
            tx.assert_not_called()

    def test_retired_sheet_and_csv_fail_before_accessing_employee_records(self):
        raw = '사번,이름,기간,평정명,삭제\n123,예시,2026,예시,Y'.encode()
        with patch.object(admin_io.db, 'all_') as rows:
            with self.assertRaises(ApiError):
                admin_io.rows('hr', '평정')
            for hint in ('직원', '평정', None):
                with self.subTest(hint=hint), self.assertRaises(ApiError):
                    admin_io.preview('hr', 1, 'legacy.csv', raw, hint)
            rows.assert_not_called()
