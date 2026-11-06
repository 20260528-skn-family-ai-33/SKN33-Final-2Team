"""#124 공유 DB의 모델·입력 계약과 전체 BGE 검색 경로를 외부 연결 없이 확인한다."""
import io
import json
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')
from app import bge_model, bge_regulation_search as regulations, bge_knowledge_search as knowledge, llm, regulation_embeddings as embeddings
from app.services import resource_rag

VECTOR = [1.] + [0.] * 1023


class SharedBgeContractTest(unittest.TestCase):
    def test_regulation_input_preserves_shared_raw_chunk_and_context(self):
        article = {'path': '취업규칙 > 제33조의4', 'chunkText': '원문\n전체',
                   'text': '가공된 본문', 'title': '화면용 제목'}
        self.assertEqual(regulations.input_text(article), '취업규칙 > 제33조의4\n\n원문\n전체')

    def test_reconstructed_legacy_input_hash_is_not_reused(self):
        stored = {'c': {'dimensions': 1024, 'input_sha256': 'same', 'input_version': 'bge-regulation-full-text-v1'}}
        self.assertEqual(regulations._missing({'c': ('raw', 'same')}, stored), ['c'])
        stored['c']['input_version'] = regulations.INPUT_VERSION
        self.assertEqual(regulations._missing({'c': ('raw', 'same')}, stored), [])

    def test_read_shared_tables_not_old_sidecars(self):
        self.assertEqual(regulations.TABLE, 'regulations.rag_chunk_embeddings')
        self.assertEqual(knowledge.TABLE, 'knowledge.chunks')
        self.assertEqual(resource_rag.MODEL, bge_model.MODEL)
        self.assertEqual(resource_rag.DIMENSIONS, 1024)

    def test_wrong_revision_pooling_normalization_or_weights_fail(self):
        base = {'model': bge_model.MODEL, **bge_model.PROVENANCE,
                'data': [{'index': 0, 'embedding': VECTOR}]}
        for key in bge_model.PROVENANCE:
            for bad in ('wrong', None):
                response = dict(base, **{key: bad})
                with self.subTest(key=key, bad=bad), patch.object(llm, '_http', return_value=io.BytesIO(json.dumps(response).encode())):
                    with self.assertRaises(llm.LlmError):
                        embeddings.embed(['query'])

    def test_resource_queries_use_bge_and_never_openai(self):
        resource_rag.cached_vectors.cache_clear()
        self.addCleanup(resource_rag.cached_vectors.cache_clear)
        with patch.object(embeddings, 'embed', return_value=[VECTOR]) as bge, patch.object(llm, 'embed', side_effect=AssertionError('OpenAI called')):
            self.assertEqual(resource_rag.cached_vectors(('query',)), (tuple(VECTOR),))
        bge.assert_called_once_with(['query'])

    def test_resource_dimension_validation_is_still_enforced(self):
        with self.assertRaises(resource_rag.RecommendationError):
            resource_rag.validate_vectors([[1.] * 1536], 1)

    def test_resource_search_filters_model_revision_source_and_price(self):
        with patch.object(resource_rag.db, 'all_', return_value=[]) as query:
            resource_rag.search_vectors('courses', ['c'], VECTOR, 20, True)
        sql = query.call_args.args[0]
        self.assertIn('p.source_sha256=e.input_sha256', sql)
        self.assertIn('e.input_version=', sql)
        self.assertIn('m.cost_won=0', sql)
        self.assertEqual(query.call_args.kwargs['model'], bge_model.MODEL)
        self.assertEqual(query.call_args.kwargs['revision'], bge_model.REVISION)
        self.assertEqual(query.call_args.kwargs['dims'], 1024)

    def test_knowledge_preview_does_not_apply_openai_ddl(self):
        with patch.object(knowledge.db, 'val', return_value=knowledge.TABLE), patch.object(knowledge.db.engine, 'raw_connection') as write:
            knowledge.install_schema()
        write.assert_not_called()
