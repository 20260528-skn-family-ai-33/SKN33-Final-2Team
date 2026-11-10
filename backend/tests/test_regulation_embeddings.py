"""규정 전용 BGE 연결·실패·모델 격리·색인 갱신을 외부 연결 없이 검사한다."""
from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import unittest
import urllib.error
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app import bge_regulation_search as search, config, llm, regulation_embeddings as embeddings, regstore

VECTOR = [1.0] + [0.0] * 1023


def indexed(vector=VECTOR):
    return embeddings.IndexedEmbedding(vector, 'bge-m3/cls-l2-fp32/v1', 3)


def stored_row(sha='sha', **changes):
    return {'dimensions': 1024, 'input_sha256': sha, 'input_version': search.INPUT_VERSION,
            'meta_sha256': sha, 'actual_input_sha256': sha,
            'model_revision': embeddings.PROVENANCE['model_revision'],
            'protocol': 'bge-m3/cls-l2-fp16/v1', 'token_count': 3, **changes}


class RegulationEmbeddingTest(unittest.TestCase):
    def setUp(self):
        self.settings = patch.dict(os.environ, BGE_M3_BASE_URL='http://127.0.0.1:18671/v1', BGE_M3_TIMEOUT='15', ASSISTANT_SEARCH_MODE='vector')
        self.settings.start()
        self.addCleanup(self.settings.stop)

    def response(self, result):
        payload = {**embeddings.PROVENANCE, **result} if isinstance(result, dict) else result
        return patch.object(llm, '_http', return_value=io.BytesIO(json.dumps(payload).encode()))

    def test_bge_orders_inputs_and_does_not_call_openai(self):
        rows = [{'index': 1, 'embedding': VECTOR}, {'index': 0, 'embedding': list(reversed(VECTOR))}]
        with self.response({'model': embeddings.BGE_MODEL, 'data': rows}) as http, patch.object(llm, 'openai') as openai:
            self.assertEqual(embeddings.embed(['첫 문서', '두 번째']), [list(reversed(VECTOR)), VECTOR])
        self.assertEqual(http.call_args.args[0], 'http://127.0.0.1:18671/v1/embeddings')
        self.assertEqual(http.call_args.args[1]['model'], embeddings.BGE_MODEL)
        self.assertEqual(http.call_args.args[3], 15)
        openai.assert_not_called()

    def test_removed_openai_embedding_client_and_setting(self):
        self.assertFalse(hasattr(llm, 'embed'))
        self.assertFalse(hasattr(llm, 'embed_model'))
        self.assertFalse(hasattr(config.S, 'openai_embed'))
        self.assertEqual(embeddings.model(), embeddings.BGE_MODEL)

    def test_full_body_is_not_truncated_at_6000_characters(self):
        article = {'reg': 'test', 'no': '제1조', 'title': '긴 조항', 'chapter': '', 'text': '본문' * 3500 + '끝'}
        article.update(path='규정 > 제1조', chunkText=article['text'])
        with patch.object(regstore, 'data', return_value={'regs': {'test': {'name': '규정'}}}):
            text = search.input_text(article)
        self.assertTrue(text.endswith(article['text']))
        self.assertIn('규정', text)

    def test_both_generation_modes_route_regulations_to_bge(self):
        for mode in ('ollama', 'openai'):
            with self.subTest(mode=mode), patch.object(search, 'search', return_value=[{'id': 'a', 'score': 1}]) as bge, patch.object(llm, 'openai') as old:
                self.assertEqual(regstore.search('질문', 5, '일반직', mode, all_groups=True), [{'id': 'a', 'score': 1}])
                bge.assert_called_once_with('질문', 5, '일반직', all_groups=True)
                old.assert_not_called()

    def test_bge_failure_does_not_fallback_to_openai_or_keywords(self):
        with patch.object(search, 'search', side_effect=llm.LlmError('BGE-M3 연결 실패')), patch.object(llm, 'openai') as old, patch.object(regstore, 'keyword_search') as keyword:
            with self.assertRaises(llm.LlmError):
                regstore.search('질문', 4, '일반직', 'ollama')
            old.assert_not_called()
            keyword.assert_not_called()

    def test_mock_uses_keywords_even_with_bge_selected(self):
        with patch.dict(os.environ, REGULATION_EMBED_PROVIDER='bge-m3'), patch.object(regstore, 'keyword_search', return_value=[]) as keyword, patch.object(search, 'search') as bge:
            self.assertEqual(regstore.search('질문', 4, '일반직', 'mock'), [])
            keyword.assert_called_once()
            bge.assert_not_called()

    def test_previous_provider_setting_cannot_restore_removed_model(self):
        with patch.dict(os.environ, REGULATION_EMBED_PROVIDER='openai'), patch.object(search, 'search', return_value=[]) as bge:
            self.assertEqual(regstore.search('질문', 4, '일반직', 'ollama'), [])
        bge.assert_called_once_with('질문', 4, '일반직', all_groups=False)

    def test_empty_inputs_do_not_request_and_blank_text_fails(self):
        with patch.object(llm, '_http') as http:
            self.assertEqual(embeddings.embed([]), [])
            with self.assertRaises(llm.LlmError):
                embeddings.embed([' '])
        http.assert_not_called()

    def test_bad_response_does_not_fallback(self):
        cases = [None, {}, {'model': 'other', 'data': []},
                 {'model': embeddings.BGE_MODEL, 'data': [{'index': 0, 'embedding': [1.0]}]},
                 {'model': embeddings.BGE_MODEL, 'data': [{'index': True, 'embedding': VECTOR}]},
                 {'model': embeddings.BGE_MODEL, 'data': [{'index': 1, 'embedding': VECTOR}]},
                 {'model': embeddings.BGE_MODEL, 'data': [{'index': 0, 'embedding': [0.0] * 1024}]},
                 {'model': embeddings.BGE_MODEL, 'data': [{'index': 0, 'embedding': [float('nan')] * 1024}]},
                 {'model': embeddings.BGE_MODEL, 'data': [{'index': 0, 'embedding': [True] * 1024}]}]
        for result in cases:
            with self.subTest(result=str(result)[:60]), self.response(result), patch.object(llm, 'openai') as fallback:
                with self.assertRaises(llm.LlmError):
                    embeddings.embed(['질문'])
                fallback.assert_not_called()

    def test_duplicate_indices_fail(self):
        with self.response({'model': embeddings.BGE_MODEL, 'data': [{'index': 0, 'embedding': VECTOR}] * 2}):
            with self.assertRaises(llm.LlmError):
                embeddings.embed(['첫째', '둘째'])

    def test_index_embedding_records_reported_precision_and_tokens(self):
        rows = [{'index': 1, 'embedding': VECTOR, 'token_count': 11},
                {'index': 0, 'embedding': list(reversed(VECTOR)), 'token_count': 5}]
        for precision, protocol in (('float32', 'bge-m3/cls-l2-fp32/v1'), ('float16', 'bge-m3/cls-l2-fp16/v1')):
            with self.subTest(precision=precision), self.response({'model': embeddings.BGE_MODEL, 'precision': precision, 'data': rows}):
                result = embeddings.embed_for_index(['첫째', '둘째'])
            self.assertEqual([(item.protocol, item.token_count) for item in result], [(protocol, 5), (protocol, 11)])
            self.assertEqual(result[0].vector, list(reversed(VECTOR)))

    def test_index_embedding_refuses_unknown_precision_or_token_count(self):
        good = {'index': 0, 'embedding': VECTOR, 'token_count': 3}
        cases = [{'data': [good]}, {'precision': 'float8', 'data': [good]}, {'precision': None, 'data': [good]},
                 {'precision': 'float32', 'data': [{'index': 0, 'embedding': VECTOR}]}]
        cases += [{'precision': 'float32', 'data': [dict(good, token_count=bad)]} for bad in (0, 8193, True, 1.5, '3')]
        for case in cases:
            with self.subTest(case=str(case)[:50]), self.response({'model': embeddings.BGE_MODEL, **case}):
                with self.assertRaisesRegex(llm.LlmError, '다시 빌드'):
                    embeddings.embed_for_index(['문서'])

    def test_query_embedding_still_works_before_server_rebuild(self):
        with self.response({'model': embeddings.BGE_MODEL, 'data': [{'index': 0, 'embedding': VECTOR}]}):
            self.assertEqual(embeddings.embed(['질문']), [VECTOR])

    def test_index_embedding_rejects_blank_input_and_skips_empty_list(self):
        with patch.object(llm, '_http') as http:
            self.assertEqual(embeddings.embed_for_index([]), [])
            with self.assertRaises(llm.LlmError):
                embeddings.embed_for_index([' '])
        http.assert_not_called()

    def test_large_batches_split_without_changing_input_order(self):
        texts = ['가' * 3000, '나' * 3000, '짧은 문서']
        with patch.object(embeddings, '_bge_request', side_effect=lambda batch: [VECTOR for _ in batch]) as request:
            self.assertEqual(len(embeddings.embed(texts)), 3)
        self.assertEqual([call.args[0] for call in request.call_args_list], [texts[:1], texts[1:]])

    def test_preview_index_does_not_embed_or_write(self):
        from tools import index_regulations
        with patch.object(regstore, 'data', return_value={'arts': {'a': {'id': 'a'}}}), patch.object(search, 'ensure_vectors') as ensure, patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(index_regulations.main([]), 0)
        ensure.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['database_writes'], 0)

    def test_non_json_and_network_failures_are_sanitized(self):
        errors = [(socket.timeout(), '시간 초과'),
                  (urllib.error.URLError('secret.internal'), '연결 실패'),
                  (urllib.error.URLError(socket.timeout()), '시간 초과'),
                  (ConnectionResetError('secret'), '연결 실패'),
                  (urllib.error.HTTPError('secret', 503, 'secret', {}, None), 'HTTP 503')]
        for error, expected in errors:
            with self.subTest(expected=expected), patch.object(llm, '_http', side_effect=error):
                with self.assertRaises(llm.LlmError) as raised:
                    embeddings.embed(['질문'])
                self.assertIn(expected, str(raised.exception))
                self.assertNotIn('secret', str(raised.exception))
        with patch.object(llm, '_http', return_value=io.BytesIO(b'<html>secret</html>')):
            with self.assertRaisesRegex(llm.LlmError, 'JSON'):
                embeddings.embed(['질문'])

    def test_bge_search_only_queries_matching_model_dimensions_and_pool(self):
        with patch.object(regstore, 'pool', return_value=[{'id': 'a'}]), patch.object(search, '_inputs', return_value={'a': ('text', 'sha')}), patch.object(search, '_stored', return_value={'a': stored_row()}), patch.object(embeddings, 'embed', return_value=[VECTOR]), patch.object(regstore.db, 'all_', return_value=[{'rag_chunk_id': 'a', 'score': .9}]) as query, patch.object(regstore.db, 'tx') as tx:
            self.assertEqual(search.search('병가', 4, '일반직'), [{'id': 'a', 'score': .9}])
        tx.assert_not_called()
        self.assertIn('regulations.rag_chunk_embeddings', query.call_args.args[0])
        self.assertEqual(query.call_args.kwargs['m'], embeddings.BGE_MODEL)
        self.assertEqual(query.call_args.kwargs['d'], 1024)
        self.assertEqual(query.call_args.kwargs['i'], ['a'])

    def test_failure_does_not_search_keywords(self):
        with patch.object(regstore, 'pool', return_value=[{'id': 'a'}]), patch.object(search, '_inputs', return_value={'a': ('text', 'sha')}), patch.object(search, '_stored', return_value={'a': stored_row()}), patch.object(embeddings, 'embed', side_effect=llm.LlmError('BGE-M3 연결 실패')), patch.object(regstore, 'keyword_search') as keyword:
            with self.assertRaises(llm.LlmError):
                search.search('질문', 4, '일반직')
            keyword.assert_not_called()

    def test_matching_hash_skips_but_stale_hash_updates_only_auxiliary_table(self):
        sha = hashlib.sha256('본문'.encode()).hexdigest()
        for stored_sha, expected in [(sha, 0), ('old', 1)]:
            row = {'rag_chunk_id': 'a', **stored_row(stored_sha)}
            with self.subTest(stored_sha=stored_sha), patch.object(regstore.db, 'all_', return_value=[row]), patch.object(regstore, 'article', return_value={}), patch.object(search, 'input_text', return_value='본문'), patch.object(embeddings, 'embed_for_index', return_value=[indexed()]) as embed, patch.object(regstore.db, 'tx') as tx:
                tx.return_value.__enter__.return_value.all.return_value = [{'rag_chunk_id': 'a', 'current_sha': sha}]
                self.assertEqual(search.ensure_vectors(['a']), expected)
                if expected:
                    sql = tx.return_value.__enter__.return_value.run.call_args
                    self.assertIn('INSERT INTO regulations.rag_chunk_embeddings', sql.args[0])
                    self.assertIn('DO UPDATE', sql.args[0])
                    self.assertEqual(sql.kwargs['s'], sha)
                else:
                    embed.assert_not_called()
                    tx.assert_not_called()

    def test_incomplete_document_batch_is_not_written(self):
        with patch.object(regstore.db, 'all_', return_value=[]), patch.object(regstore, 'article', return_value={}), patch.object(search, 'input_text', return_value='본문'), patch.object(embeddings, 'embed_for_index', return_value=[]), patch.object(regstore.db, 'tx') as tx:
            with self.assertRaises(llm.LlmError):
                search.ensure_vectors(['a'])
            tx.assert_not_called()

    def test_missing_index_fails_without_embedding_or_writing(self):
        with patch.object(regstore, 'pool', return_value=[{'id': 'a'}]), patch.object(search, '_inputs', return_value={'a': ('text', 'sha')}), patch.object(search, '_stored', return_value={}), patch.object(embeddings, 'embed') as embed, patch.object(regstore.db, 'tx') as tx:
            with self.assertRaisesRegex(llm.LlmError, '색인'):
                search.search('질문', 4, '일반직')
            embed.assert_not_called()
            tx.assert_not_called()


class RegulationConfigTest(unittest.TestCase):
    def request(self, values):
        with patch.dict(os.environ, values, clear=True), patch.object(config, '_FILE', {}):
            with patch.object(llm, '_http', return_value=io.BytesIO(json.dumps({**embeddings.PROVENANCE, 'model': embeddings.BGE_MODEL, 'data': [{'index': 0, 'embedding': VECTOR}]}).encode())) as http:
                embeddings.embed(['질문'])
                return http.call_args

    def test_default_is_independent_local_bge_server(self):
        self.assertEqual(self.request({}).args[0], 'http://127.0.0.1:18671/v1/embeddings')

    def test_bge_requires_valid_base_url(self):
        for address in ('', 'ftp://localhost/v1', 'http://user:secret@localhost/v1', 'http://localhost/v1?key=secret'):
            if not address:
                continue
            with self.subTest(address=address), self.assertRaises(llm.LlmError):
                self.request({'BGE_M3_BASE_URL': address})
        self.assertEqual(self.request({'BGE_M3_BASE_URL': 'http://localhost:18671/v1/'}).args[0], 'http://localhost:18671/v1/embeddings')

    def test_invalid_timeout_fails(self):
        for value in ('0', '601', 'bad'):
            with self.subTest(value=value), self.assertRaises(llm.LlmError):
                self.request({'BGE_M3_TIMEOUT': value})
