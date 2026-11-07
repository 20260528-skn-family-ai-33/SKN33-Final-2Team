"""BGE 자료 색인의 갱신·저장 격리·범주 필터·실패를 외부 연결 없이 확인한다."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app import bge_knowledge_search as search, config, knowledge, llm, regulation_embeddings as embeddings
from tools import index_knowledge

VECTOR = [1.0] + [0.0] * 1023


def chunk(text='등록 자료 원문'):
    return {'chunk_id': 'c1', 'chunk_text': text,
            'chunk_text_sha256': hashlib.sha256(text.encode()).hexdigest()}


class KnowledgeEmbeddingTest(unittest.TestCase):
    def setUp(self):
        settings = patch.dict(os.environ, ASSISTANT_SEARCH_MODE='vector')
        settings.start()
        self.addCleanup(settings.stop)

    def test_both_categories_use_bge_without_openai(self):
        with patch.object(search, 'search', return_value=[]) as bge, patch.object(llm, 'openai') as old:
            knowledge.search_company('회사 소개')
            knowledge.search_life('식당 안내')
        self.assertEqual(bge.call_args_list[0].args, ('회사 소개', knowledge.CATEGORY))
        self.assertEqual(bge.call_args_list[1].args, ('식당 안내', knowledge.LIFE_CATEGORY))
        old.assert_not_called()

    def test_default_provider_is_bge(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(config, '_FILE', {}), patch.object(search, 'search', return_value=[]) as bge:
            self.assertEqual(knowledge.search_company('질문'), [])
        bge.assert_called_once_with('질문', knowledge.CATEGORY)

    def test_search_keeps_categories_provenance_and_virtual_filter(self):
        for category, real_only in ((knowledge.CATEGORY, True), (knowledge.LIFE_CATEGORY, False)):
            hit = {'chunk_id': 'c1', 'category': category, 'is_virtual': not real_only,
                   'metadata': {'source': '원문'}, 'document_title': '자료'}
            with self.subTest(category=category), patch.object(search.db, 'val', return_value=search.TABLE), patch.object(search.db, 'one', return_value={'total': 2, 'indexed': 2}), patch.object(embeddings, 'embed', return_value=[VECTOR]), patch.object(search.db, 'all_', return_value=[hit]) as sql, patch.object(search.db, 'tx') as write, patch.object(llm, 'openai') as old:
                self.assertEqual(search.search('질문', category), [hit])
            self.assertEqual(sql.call_args.kwargs['category'], category)
            self.assertEqual(sql.call_args.kwargs['real_only'], real_only)
            self.assertEqual(sql.call_args.kwargs['model'], 'BAAI/bge-m3')
            self.assertEqual(sql.call_args.kwargs['dims'], 1024)
            self.assertIn('v.input_sha256=c.chunk_text_sha256', sql.call_args.args[0])
            self.assertEqual(sql.call_args.kwargs['limit'], 5)
            write.assert_not_called()
            old.assert_not_called()

    def test_missing_schema_is_actionable_error(self):
        with patch.object(search.db, 'val', return_value=None), patch.object(embeddings, 'embed') as embed:
            with self.assertRaisesRegex(llm.LlmError, 'index_knowledge.py --apply'):
                search.search('질문', knowledge.CATEGORY)
        embed.assert_not_called()

    def test_empty_category_has_no_embedding_call(self):
        with patch.object(search.db, 'val', return_value=search.TABLE), patch.object(search.db, 'one', return_value={'total': 0}), patch.object(embeddings, 'embed') as embed:
            self.assertEqual(search.search('질문', knowledge.CATEGORY), [])
        embed.assert_not_called()

    def test_partial_or_stale_index_fails_before_query_embedding(self):
        for indexed in (0, 1):
            with self.subTest(indexed=indexed), patch.object(search.db, 'val', return_value=search.TABLE), patch.object(search.db, 'one', return_value={'total': 2, 'indexed': indexed}), patch.object(embeddings, 'embed') as embed:
                with self.assertRaisesRegex(llm.LlmError, '벡터가 없거나 원문과 달라요'):
                    search.search('질문', knowledge.LIFE_CATEGORY)
                embed.assert_not_called()

    def test_connection_failure_has_no_fallback(self):
        with patch.object(search.db, 'val', return_value=search.TABLE), patch.object(search.db, 'one', return_value={'total': 1, 'indexed': 1}), patch.object(embeddings, 'embed', side_effect=llm.LlmError('BGE-M3 연결 실패')), patch.object(llm, 'openai') as old:
            with self.assertRaisesRegex(llm.LlmError, '연결 실패'):
                knowledge.search_company('질문')
        old.assert_not_called()

    def test_invalid_inputs_fail_before_db_access(self):
        with patch.object(search.db, 'val') as query:
            for question, category in ((' ', knowledge.CATEGORY), ('질문', '다른 범주')):
                with self.assertRaises(llm.LlmError):
                    search.search(question, category)
        query.assert_not_called()

    def test_invalid_query_vector_never_reaches_sql(self):
        with patch.object(search.db, 'val', return_value=search.TABLE), patch.object(search.db, 'one', return_value={'total': 1, 'indexed': 1}), patch.object(embeddings, 'embed', return_value=[[1.0] * 1536]), patch.object(search.db, 'all_') as query:
            with self.assertRaises(llm.LlmError):
                search.search('질문', knowledge.CATEGORY)
        query.assert_not_called()

    def test_identical_input_reuses_stored_vector(self):
        source = chunk()
        stored = dict(source, input_sha256=source['chunk_text_sha256'], dimensions=1024)
        with patch.object(search.db, 'all_', return_value=[stored]), patch.object(embeddings, 'embed') as embed, patch.object(search.db, 'tx') as write:
            self.assertEqual(search.ensure_vectors([source]), 0)
        embed.assert_not_called()
        write.assert_not_called()

    def test_changed_and_missing_inputs_upsert_only_separate_table(self):
        source = chunk('긴 원문' * 2000)
        for stored in ([], [{'chunk_id': 'c1', 'input_sha256': 'old', 'dimensions': 1024}]):
            transaction = Mock()
            transaction.run.return_value = 1

            @contextmanager
            def tx():
                yield transaction

            with self.subTest(stored=stored), patch.object(search.db, 'all_', return_value=stored), patch.object(embeddings, 'embed', return_value=[VECTOR]) as embed, patch.object(search.db, 'tx', tx):
                self.assertEqual(search.ensure_vectors([source]), 1)
            embed.assert_called_once_with([source['chunk_text']])
            self.assertIn('UPDATE knowledge.chunks', transaction.run.call_args.args[0])
            self.assertNotIn('INSERT INTO', transaction.run.call_args.args[0])
            self.assertEqual(transaction.run.call_args.kwargs['dims'], 1024)

    def test_bad_source_hash_and_invalid_vectors_never_write(self):
        bad = dict(chunk(), chunk_text_sha256='bad')
        with patch.object(search.db, 'tx') as write:
            with self.assertRaisesRegex(llm.LlmError, '원문 해시'):
                search.ensure_vectors([bad])
            for vector in ([0.0] * 1024, [1.0] * 1536, [float('nan')] * 1024):
                with patch.object(search.db, 'all_', return_value=[]), patch.object(embeddings, 'embed', return_value=[vector]):
                    with self.assertRaises(llm.LlmError):
                        search.ensure_vectors([chunk()])
        write.assert_not_called()

    def test_interrupted_index_resumes_without_reembedding_committed_batches(self):
        chunks = [dict(chunk(f'원문 {index}'), chunk_id=f'c{index}') for index in range(5)]
        stored = {}
        transaction = Mock()

        def save(sql, **params):
            stored[params['id']] = {'chunk_id': params['id'], 'dimensions': params['dims'],
                                    'input_sha256': params['sha']}
            return 1

        transaction.run.side_effect = save

        @contextmanager
        def tx():
            yield transaction

        with patch.object(search.db, 'all_', side_effect=lambda *a, **kw: list(stored.values())), patch.object(search.db, 'tx', tx):
            with patch.object(embeddings, 'embed', side_effect=[[VECTOR] * 4, llm.LlmError('BGE-M3 연결 실패')]):
                with self.assertRaises(llm.LlmError):
                    search.ensure_vectors(chunks)
            self.assertEqual(len(stored), 4)
            with patch.object(embeddings, 'embed', return_value=[VECTOR]) as embed:
                self.assertEqual(search.ensure_vectors(chunks), 1)
                embed.assert_called_once_with([chunks[-1]['chunk_text']])
            self.assertEqual(len(stored), 5)

    def test_preview_never_installs_schema_embeds_or_writes(self):
        with patch.object(search, 'source_chunks', return_value=[chunk()]), patch.object(search, 'install_schema') as schema, patch.object(search, 'ensure_vectors') as write, patch('builtins.print'):
            self.assertEqual(index_knowledge.main([]), 0)
        schema.assert_not_called()
        write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
