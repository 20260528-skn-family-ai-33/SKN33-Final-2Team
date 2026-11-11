"""HR 양식에 남아 있는 구버전 평정 데이터를 직원 변경으로 해석하지 않는다."""
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

    def test_retired_sheet_and_csv_fail_before_accessing_employee_records(self):
        raw = '사번,이름,기간,평정명,삭제\n123,예시,2026,예시,Y'.encode()
        with patch.object(admin_io.db, 'all_') as rows:
            with self.assertRaises(ApiError):
                admin_io.rows('hr', '평정')
            for hint in ('직원', '평정', None):
                with self.subTest(hint=hint), self.assertRaises(ApiError):
                    admin_io.preview('hr', 1, 'legacy.csv', raw, hint)
            rows.assert_not_called()
