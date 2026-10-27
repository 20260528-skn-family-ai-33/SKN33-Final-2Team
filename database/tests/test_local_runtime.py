"""Native path decoding and refusal to operate on another PostgreSQL cluster."""
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from src.database import local_runtime


class LocalRuntimeTests(unittest.TestCase):
    def connection(self, raw):
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {
            'data_directory': raw,
        }
        return conn

    def test_utf8_korean_path(self):
        path = Path('runtime') / 'DB설계' / 'postgres'
        actual = local_runtime.server_data_directory(self.connection(str(path).encode('utf-8')))
        self.assertEqual(actual, path)

    @unittest.skipUnless(os.name == 'nt', 'Windows native encoding only')
    def test_windows_native_korean_path(self):
        path = Path('runtime') / 'DB설계' / 'postgres'
        actual = local_runtime.server_data_directory(self.connection(str(path).encode('mbcs')))
        self.assertEqual(actual, path)

    def test_invalid_native_bytes_are_not_silently_replaced(self):
        with self.assertRaises(UnicodeDecodeError):
            local_runtime.server_data_directory(self.connection(b'\x81'))

    def test_status_refuses_another_cluster(self):
        with patch.object(local_runtime, 'run_control', return_value=0), \
             patch.object(local_runtime, 'connect'), \
             patch.object(local_runtime, 'server_data_directory', return_value=Path('another_cluster')):
            with self.assertRaisesRegex(ValueError, 'another PostgreSQL instance'):
                local_runtime.status()

    def test_backup_refuses_another_cluster_before_writing(self):
        destination = local_runtime.ROOT / 'data/local_db/runtime_guard_test_unused.dump'
        self.assertFalse(destination.exists())
        with patch.object(local_runtime, 'connect'), \
             patch.object(local_runtime, 'server_data_directory', return_value=Path('another_cluster')), \
             patch.object(local_runtime, 'native_bin') as binary:
            with self.assertRaisesRegex(ValueError, 'unexpected database'):
                local_runtime.backup(destination)
        binary.assert_not_called()
        self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
