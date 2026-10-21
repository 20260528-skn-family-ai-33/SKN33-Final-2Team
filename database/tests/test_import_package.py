"""External asset failures must occur before credentials or a DB are touched."""
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.database import deployment, erd, portable


class ImportPackageTests(unittest.TestCase):
    def test_missing_external_archive_fails_before_password_or_connection(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            args = SimpleNamespace(archive=Path(directory) / "missing.dump")
            with patch.object(portable.getpass, "getpass") as password, patch.object(portable.psycopg, "connect") as connect:
                with self.assertRaisesRegex(ValueError, "external .dump"):
                    portable.restore(args)
                password.assert_not_called()
                connect.assert_not_called()

    def test_archive_checksum_mismatch_fails_before_password_or_connection(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            archive = Path(directory) / "example.dump"
            archive.write_bytes(b"not a database")
            archive.with_suffix(".manifest.json").write_text(json.dumps({"sha256": "0" * 64}), encoding="utf-8")
            args = SimpleNamespace(archive=archive)
            with patch.object(portable.getpass, "getpass") as password, patch.object(portable.psycopg, "connect") as connect:
                with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                    portable.restore(args)
                password.assert_not_called()
                connect.assert_not_called()

    def test_external_employee_seed_is_required_before_database_work(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            with patch.object(deployment, "ROOT", Path(directory)), patch.object(deployment, "check_schema") as check:
                with self.assertRaisesRegex(ValueError, "Employee seed data are external"):
                    deployment.demo_users(None)
                check.assert_not_called()


class ErdTemplateTests(unittest.TestCase):
    def test_schema_refresh_preserves_external_layout_and_controls(self):
        root = Path(__file__).resolve().parents[2]
        template = (root / "docs/07_데이터베이스_저장소_설계/ERD_최종.html").read_text(encoding="utf-8")
        data = {"public.example": {"rows": 3}}
        result = erd.render_html(data, template)
        self.assertIn("function setupTableDrag()", result)
        self.assertIn("#layoutExport", result)
        self.assertIn("function roundPath(", result)
        match = re.search(r"const\s+D\s*=\s*", result)
        self.assertEqual(json.JSONDecoder().raw_decode(result[match.end():])[0], data)

    def test_invalid_template_fails_instead_of_building_another_layout(self):
        for template in ("<style>body{}</style>", "const D = window.data;", 'const D = {"a": 1} alert(1)'):
            with self.subTest(template=template), self.assertRaises(ValueError):
                erd.render_html({}, template)

    def test_schema_text_cannot_close_the_script_element(self):
        data = {"label": "</script><script>alert(1)</script>"}
        result = erd.render_html(data, '<script>const D = {};</script>')
        self.assertEqual(result.count("</script>"), 1)
        match = re.search(r"const\s+D\s*=\s*", result)
        self.assertEqual(json.JSONDecoder().raw_decode(result[match.end():])[0], data)


if __name__ == "__main__":
    unittest.main()
