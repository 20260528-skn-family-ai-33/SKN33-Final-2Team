"""Dependency-free unit tests for src.database.vectors.regulation_vectors and V11 regulation RAG grounding."""
import hashlib
import json
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.database.vectors import regulation_vectors as rv


class RegulationVectorTests(unittest.TestCase):
    def test_input_text_and_hash_strip_null_bytes(self):
        row = {
            "rag_chunk_id": "c1",
            "context_path": "인재개발규정 > 별표 1",
            "chunk_text": "일반직 4급\x00 80시간",
        }
        cleaned = rv.input_text(row)
        self.assertNotIn("\x00", cleaned)
        self.assertEqual(cleaned, "인재개발규정 > 별표 1\n\n일반직 4급 80시간")
        expected_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        self.assertEqual(rv.input_hash(row), expected_hash)

    def test_long_bge_input_is_not_truncated(self):
        from src.shared.bge_embeddings import MODEL, PROVENANCE, embed_texts
        text = '가나다라마바사아자차카타파하 ' * 400
        client = MagicMock(return_value={'model': MODEL, **PROVENANCE,
            'data': [{'index': 0, 'embedding': [1.] + [0.] * 1023}]})
        embed_texts([text], client=client)
        self.assertEqual(client.call_args.args[0]['input'], [text])

    def test_vector_values_validation(self):
        valid = [0.01] * 1024
        self.assertEqual(len(rv.vector_values(valid)), 1024)
        self.assertEqual(len(rv.vector_values(json.dumps(valid))), 1024)
        for invalid in ([0.0] * 1024, [0.1] * 10, [float("nan")] * 1024):
            with self.assertRaisesRegex(ValueError, "Invalid regulation vector"):
                rv.vector_values(invalid)

    def test_unchanged_vector_requires_matching_metadata(self):
        row = {'rag_chunk_id': 'c1', 'context_path': '규정', 'chunk_text': '본문'}
        sha = rv.input_hash(row)
        current = {'input_version': rv.INPUT_VERSION, 'input_sha256': sha,
                   'dimensions': rv.DIMENSIONS, 'meta_sha256': sha, 'actual_input_sha256': sha,
                   'model_revision': rv.PROVENANCE['model_revision'], 'protocol': rv.PROTOCOL,
                   'token_count': 3}
        self.assertFalse(rv.needs_embedding(row, {'c1': current}))
        self.assertTrue(rv.needs_embedding(row, {}))
        for field, bad in (('meta_sha256', None), ('meta_sha256', 'old'),
                           ('actual_input_sha256', 'old'), ('model_revision', 'old'),
                           ('dimensions', 1536), ('protocol', 'old'),
                           ('token_count', 0), ('token_count', 8193)):
            with self.subTest(field=field, bad=bad):
                self.assertTrue(rv.needs_embedding(row, {'c1': dict(current, **{field: bad})}))

    def test_missing_metadata_table_stops_before_embedding_or_schema_writes(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {'id': None}
        with patch.object(rv, 'sources', return_value=[{'rag_chunk_id': 'c1'}]), \
             patch.object(rv, 'embed_texts') as embed:
            with self.assertRaisesRegex(ValueError, 'Restore the shared BGE-M3 database'):
                rv.embed(conn)
        conn.execute.assert_called_once_with('SELECT to_regclass(%s) AS id', (rv.META_TABLE,))
        conn.commit.assert_not_called()
        embed.assert_not_called()

    def test_import_rejects_unverified_model_provenance_before_database_access(self):
        for version, provenance in ((1, None), (2, dict(rv.PROVENANCE, model_revision='unknown'))):
            with self.subTest(version=version), TemporaryDirectory() as directory:
                payload = json.dumps({'format_version': version, 'provenance': provenance})
                path = Path(directory) / 'vectors.json'
                path.write_text(json.dumps({'payload': payload,
                    'sha256': hashlib.sha256(payload.encode('utf-8')).hexdigest()}), encoding='utf-8')
                conn = MagicMock()
                with self.assertRaisesRegex(ValueError, 'provenance missing/mismatched'):
                    rv.import_vectors(conn, path)
                conn.execute.assert_not_called()



if __name__ == "__main__":
    unittest.main(verbosity=2)
