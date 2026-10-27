"""Evidence fidelity and category boundaries; no paid API calls."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from src.database.ingestion.knowledge_documents import load_files, validate_rows, reconstruct, prepare, search


def fixture(index=1):
    text = '  본사 시설 안내입니다.\n원문 공백과 줄바꿈을 유지합니다.  '
    return {'chunk_id': f'test-{index}', 'category': '사내 생활안내', 'document_id': 'test-guide',
            'document_title': '검증 안내', 'document_kind': 'guide', 'display_order': index,
            'chunk_text': text, 'chunk_text_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'is_virtual': True, 'source_url': None, 'source_limits': '가상 자료',
            'training_split': 'test', 'topic_id': 'W001'}


class KnowledgeDocumentTests(unittest.TestCase):
    def test_verbatim_text_and_all_metadata_roundtrip(self):
        original = fixture()
        validate_rows([original])
        stored = {k: v for k, v in original.items() if k not in ('source_url', 'source_limits', 'training_split', 'topic_id')}
        stored['metadata'] = {k: original[k] for k in ('source_url', 'source_limits', 'training_split', 'topic_id')}
        self.assertEqual(reconstruct(stored), original)
        self.assertTrue(stored['chunk_text'].startswith('  '))

    def test_changed_hash_rejected(self):
        row = fixture()
        row['chunk_text'] += '변경'
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            validate_rows([row])

    def test_duplicate_and_conflicting_document_are_rejected(self):
        with self.assertRaisesRegex(ValueError, '중복'):
            validate_rows([fixture(), fixture()])
        other = fixture(2)
        other['category'] = '수자원공사 정보'
        with self.assertRaisesRegex(ValueError, '같은 문서'):
            validate_rows([fixture(), other])

    def test_virtual_flag_and_order_require_exact_types(self):
        for key, value in (('is_virtual', 'false'), ('display_order', True), ('display_order', 0)):
            row = fixture()
            row[key] = value
            with self.assertRaises(ValueError):
                validate_rows([row])

    def test_oversize_stops_without_truncation(self):
        row = fixture()
        row['chunk_text'] = '가' * 2700
        row['chunk_text_sha256'] = hashlib.sha256(row['chunk_text'].encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, '자르지 않고'):
            validate_rows([row])
        self.assertEqual(len(row['chunk_text']), 2700)

    def test_search_rejects_missing_or_regulation_category_before_api(self):
        client, conn = MagicMock(), MagicMock()
        for category in (None, '', '규정'):
            with self.assertRaises(ValueError):
                search(conn, '문의', category=category, client=client)
        for kwargs in ({'limit': 0}, {'threshold': float('nan')}):
            with self.assertRaises(ValueError):
                search(conn, '문의', category='사내 생활안내', client=client, **kwargs)
        client.embeddings.create.assert_not_called()
        conn.execute.assert_not_called()

    def test_existing_source_change_stops_before_write(self):
        row = fixture()
        changed = copy.deepcopy(row)
        changed['source_limits'] = '다른 출처'
        old = {**row, 'metadata': {k: row[k] for k in ('source_url', 'source_limits', 'training_split', 'topic_id')},
               'embedding': '[1]', 'embedding_model': 'text-embedding-3-small', 'input_sha256': row['chunk_text_sha256']}
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {'id': 'knowledge.chunks'}
        conn.execute.return_value.fetchall.side_effect = [[old], [{'document_id': row['document_id'], 'category': row['category'], 'title': row['document_title'], 'document_kind': row['document_kind']}]]
        with self.assertRaisesRegex(ValueError, '덮어쓰지'):
            prepare(conn, [changed])
        self.assertFalse(any('INSERT' in str(call) or 'UPDATE' in str(call) for call in conn.execute.call_args_list))

    def test_partial_deliverable_file_is_rejected(self):
        path = Path('workplace_guide_chunks.jsonl')
        with patch.object(Path, 'read_bytes', return_value=json.dumps(fixture(), ensure_ascii=False).encode('utf-8')):
            with self.assertRaisesRegex(ValueError, '예상 조각 수'):
                load_files([path])


if __name__ == '__main__':
    unittest.main()
