"""DB 도구의 BGE 모델·응답·원문 보존·실패 계약을 외부 연결 없이 검사한다."""
import os
import unittest
from unittest.mock import Mock, patch

from src.shared import bge_embeddings as bge
from src.database import deployment

VECTOR = [1.] + [0.] * 1023


def response(texts):
    return {'model': bge.MODEL, **bge.PROVENANCE,
            'data': [{'index': i, 'embedding': VECTOR} for i in range(len(texts))]}


class BgeEmbeddingTests(unittest.TestCase):
    def test_batches_preserve_full_input_and_order_without_openai_key(self):
        texts = [' 원문 ' * 3000] + [f'본문 {i}' for i in range(6)]
        client = Mock(side_effect=lambda payload: response(payload['input']))
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            self.assertEqual(bge.embed_texts(texts, client), [VECTOR] * 7)
        self.assertEqual([call.args[0]['input'] for call in client.call_args_list], [texts[:4], texts[4:]])
        self.assertTrue(all(call.args[0]['model'] == 'BAAI/bge-m3' for call in client.call_args_list))

    def test_wrong_or_missing_model_provenance_fails(self):
        for key in ('model', *bge.PROVENANCE):
            for bad in (None, 'wrong'):
                payload = dict(response(['본문']), **{key: bad})
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    bge.embed_texts(['본문'], lambda _: payload)

    def test_incomplete_duplicate_or_bad_vectors_fail(self):
        for rows in ([], [{'index': 1, 'embedding': VECTOR}],
                     [{'index': 0, 'embedding': [1.] * 1536}],
                     [{'index': 0, 'embedding': [0.] * 1024}],
                     [{'index': 0, 'embedding': [float('nan')] * 1024}]):
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                bge.embed_texts(['본문'], lambda _: dict(response(['본문']), data=rows))

    def test_connection_failure_is_not_converted_to_empty_success(self):
        with patch.object(bge.urllib.request, 'urlopen', side_effect=OSError('private detail')):
            with self.assertRaisesRegex(ValueError, 'BGE-M3 서버') as caught:
                bge.embed_texts(['본문'])
        self.assertNotIn('private detail', str(caught.exception))

    def test_bad_configuration_fails_before_http(self):
        for key, value in (('BGE_M3_BASE_URL', 'http://user:secret@host/v1'),
                           ('BGE_M3_BASE_URL', 'ftp://host/v1'), ('BGE_M3_TIMEOUT', '0')):
            with patch.dict(os.environ, {key: value}), patch.object(bge.urllib.request, 'urlopen') as http:
                with self.assertRaises(ValueError):
                    bge.embed_texts(['본문'])
                http.assert_not_called()

    def test_old_database_is_rejected_before_schema_writes(self):
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = {'id': None}
        with self.assertRaisesRegex(ValueError, '공유 BGE-M3 DB'):
            deployment.migrate(conn)
        self.assertEqual(conn.execute.call_count, 1)


if __name__ == '__main__':
    unittest.main()
