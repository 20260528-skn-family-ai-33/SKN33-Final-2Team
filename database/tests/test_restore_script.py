"""복원 스크립트의 인코딩·트랜잭션 경계를 Docker 없이 확인한다. 실제 복원은 일회용 Compose에서 따로 검사한다."""
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'restore-bge-db.ps1'


class RestoreScriptTests(unittest.TestCase):
    def setUp(self):
        self.raw = SCRIPT.read_bytes()
        self.text = self.raw.decode('utf-8-sig').replace('\r\n', '\n')

    def verification(self):
        return self.text.split('$verification = @"\n', 1)[1].split('\n"@', 1)[0]

    def test_file_keeps_bom_for_windows_powershell_51(self):
        self.assertTrue(self.raw.startswith(b'\xef\xbb\xbf'))

    def test_verification_and_marker_share_one_transaction(self):
        lines = self.verification().splitlines()
        self.assertEqual((lines[0], lines[-1]), ('BEGIN;', 'COMMIT;'))
        body = '\n'.join(lines)
        self.assertLess(body.index('RAISE EXCEPTION'), body.index('CREATE TABLE IF NOT EXISTS growpath_bge_meta.restore_state'))
        self.assertLess(body.index('CREATE TABLE IF NOT EXISTS growpath_bge_meta.restore_state'),
                        body.index('INSERT INTO growpath_bge_meta.restore_state'))

    def test_common_psql_function_and_pg_restore_guards_are_unchanged(self):
        common = self.text.split('function Invoke-BgePg', 1)[1].split('\n}\n', 1)[0]
        self.assertNotIn('single-transaction', common)
        self.assertNotIn('BEGIN', common)
        self.assertIn('ON_ERROR_STOP=1', common)
        self.assertIn('pg_restore -U "$POSTGRES_USER" --single-transaction --exit-on-error', self.text)
        self.assertIn('복원 대상에 기존 테이블이 있습니다', self.text)
        self.assertIn('기존 복원 DB의 백업 해시가 다릅니다', self.text)


if __name__ == '__main__':
    unittest.main()
