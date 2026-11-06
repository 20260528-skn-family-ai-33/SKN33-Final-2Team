"""제품 VERSION 파일의 로컬·API 연결과 잘못된 배포 검사."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app.version import VERSION_PATH, read_project_version


class AppVersionTests(unittest.TestCase):
    def test_reads_version_with_trailing_newline(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'VERSION'
            path.write_text('0.2.0\n', encoding='utf-8')
            self.assertEqual(read_project_version(path), '0.2.0')

    def test_reads_changed_version_without_a_fallback_or_cache(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'VERSION'
            path.write_text('0.2.0\n', encoding='utf-8')
            self.assertEqual(read_project_version(path), '0.2.0')
            path.write_text('1.12.3\n', encoding='utf-8')
            self.assertEqual(read_project_version(path), '1.12.3')

    def test_reads_utf8_bom_with_windows_newline(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'VERSION'
            path.write_bytes(b'\xef\xbb\xbf0.2.0\r\n')
            self.assertEqual(read_project_version(path), '0.2.0')

    def test_bom_does_not_allow_invalid_version(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'VERSION'
            path.write_bytes(b'\xef\xbb\xbfv0.2.0\r\n')
            with self.assertRaisesRegex(ValueError, 'X.Y.Z'):
                read_project_version(path)

    def test_missing_version_stops_startup(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'VERSION'
            with self.assertRaisesRegex(RuntimeError, '버전 파일을 읽을 수 없어요'):
                read_project_version(path)

    def test_invalid_versions_are_rejected(self):
        invalid = ('', 'v0.2.0', '0.2', '0.2.0.1', '00.2.0', '0.02.0', '0.2.00',
                   '-1.2.3', '0.2.0-beta.1', '0.2.0+build', '０.2.0', '0.2.0\n0.2.1')
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'VERSION'
            for value in invalid:
                with self.subTest(value=value):
                    path.write_text(value, encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'X.Y.Z'):
                        read_project_version(path)

    def test_non_utf8_file_has_explicit_error(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'VERSION'
            path.write_bytes(b'\xff')
            with self.assertRaisesRegex(RuntimeError, '버전 파일을 읽을 수 없어요'):
                read_project_version(path)

    def test_openapi_uses_repository_version(self):
        from app.main import app

        expected = (Path(__file__).resolve().parents[2] / 'VERSION').read_text(encoding='utf-8-sig').strip()
        self.assertEqual(VERSION_PATH, Path(__file__).resolve().parents[2] / 'VERSION')
        self.assertEqual(app.version, expected)
        self.assertEqual(app.openapi()['info']['version'], expected)


if __name__ == '__main__':
    unittest.main()
