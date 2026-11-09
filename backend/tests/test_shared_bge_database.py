"""#124 공유 DB의 모델·입력 계약과 전체 BGE 검색 경로를 외부 연결 없이 확인한다."""
import hashlib
import io
import json
import os
import unittest
from unittest.mock import MagicMock, Mock, patch

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
        with patch.object(embeddings, 'embed', return_value=[VECTOR]) as bge, patch.object(llm, 'openai', side_effect=AssertionError('OpenAI called')):
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

    def test_regulation_ensure_vectors_updates_meta_inputs_atomically(self):
        sha = 'abc' * 21 + 'a'
        article = {'path': '취업규칙 > 제1조', 'chunkText': '본문', 'id': 'aid'}
        calls = []
        tx_mock = Mock(spec=regulations.db.Tx)
        tx_mock.all.return_value = [{'rag_chunk_id': 'aid', 'current_sha': sha}]
        tx_mock.run.side_effect = lambda sql, **kw: calls.append((sql, kw))

        from contextlib import contextmanager
        @contextmanager
        def fake_tx():
            yield tx_mock

        with patch.object(regulations.regstore, 'article', return_value=article), \
             patch.object(regulations, 'input_text', return_value='규정 본문'), \
             patch.object(regulations.hashlib, 'sha256') as h_mock, \
             patch.object(regulations, '_stored', return_value={}), \
             patch.object(embeddings, 'embed', return_value=[VECTOR]), \
             patch.object(regulations.db, 'tx', fake_tx):
            h_mock.return_value.hexdigest.return_value = sha
            updated = regulations.ensure_vectors(['aid'])

        self.assertEqual(updated, 1)
        self.assertEqual(len(calls), 2)
        meta_call = next(c for c in calls if 'growpath_bge_meta.inputs' in c[0])
        vector_call = next(c for c in calls if 'regulations.rag_chunk_embeddings' in c[0])
        self.assertEqual(meta_call[1]['s'], sha)
        self.assertEqual(meta_call[1]['proto'], 'bge-m3/cls-l2-fp16/v1')
        self.assertEqual(meta_call[1]['rev'], bge_model.REVISION)
        self.assertEqual(vector_call[1]['s'], sha)

    def test_regulation_source_change_aborts_with_error(self):
        article = {'path': '취업규칙 > 제1조', 'chunkText': '본문', 'id': 'aid'}
        tx_mock = Mock(spec=regulations.db.Tx)
        tx_mock.all.return_value = [{'rag_chunk_id': 'aid', 'current_sha': 'different_sha'}]

        from contextlib import contextmanager
        @contextmanager
        def fake_tx():
            yield tx_mock

        with patch.object(regulations.regstore, 'article', return_value=article), \
             patch.object(regulations, '_stored', return_value={}), \
             patch.object(embeddings, 'embed', return_value=[VECTOR]), \
             patch.object(regulations.db, 'tx', fake_tx):
            with self.assertRaisesRegex(llm.LlmError, '규정 원문이 바뀌었어요'):
                regulations.ensure_vectors(['aid'])

    def test_regulation_meta_mismatch_detected_as_missing(self):
        inputs = {'c': ('raw', 'hash_val')}
        # 벡터는 일치하지만 메타 레코드 해시가 다른 경우
        stored_bad_meta = {'c': {'dimensions': 1024, 'input_sha256': 'hash_val',
                                 'input_version': regulations.INPUT_VERSION,
                                 'meta_sha256': 'old_hash', 'actual_input_sha256': 'hash_val',
                                 'model_revision': bge_model.REVISION}}
        self.assertEqual(regulations._missing(inputs, stored_bad_meta), ['c'])
        # 메타 레코드 해시까지 일치하면 missing 없음
        stored_good_meta = {'c': {'dimensions': 1024, 'input_sha256': 'hash_val',
                                  'input_version': regulations.INPUT_VERSION,
                                  'meta_sha256': 'hash_val', 'actual_input_sha256': 'hash_val',
                                  'model_revision': bge_model.REVISION}}
        self.assertEqual(regulations._missing(inputs, stored_good_meta), [])

    def test_knowledge_ensure_vectors_updates_meta_inputs_atomically(self):
        text = '자료 원문'
        sha = regulations.hashlib.sha256(text.encode()).hexdigest()
        chunk_obj = {'chunk_id': 'k1', 'chunk_text': text, 'chunk_text_sha256': sha}
        calls = []
        tx_mock = Mock(spec=regulations.db.Tx)
        tx_mock.run.side_effect = lambda sql, **kw: calls.append((sql, kw)) or 1

        from contextlib import contextmanager
        @contextmanager
        def fake_tx():
            yield tx_mock

        with patch.object(knowledge.db, 'all_', return_value=[]), \
             patch.object(embeddings, 'embed', return_value=[VECTOR]), \
             patch.object(knowledge.db, 'tx', fake_tx):
            updated = knowledge.ensure_vectors([chunk_obj])

        self.assertEqual(updated, 1)
        self.assertEqual(len(calls), 2)
        meta_call = next(c for c in calls if 'growpath_bge_meta.inputs' in c[0])
        chunk_call = next(c for c in calls if 'UPDATE knowledge.chunks' in c[0])
        self.assertEqual(meta_call[1]['sha'], sha)
        self.assertEqual(meta_call[1]['proto'], 'bge-m3/cls-l2-fp16/v1')
        self.assertEqual(meta_call[1]['rev'], bge_model.REVISION)
        self.assertEqual(chunk_call[1]['sha'], sha)

    def test_verify_bge_database_supports_skipping_seed_counts(self):
        from tools import verify_bge_database as vbd
        # DB mock: valid == total 이지만 시드 개수(2984 등)와 다른 경우
        with patch.object(vbd.db, 'one', side_effect=[
            {'total': 10, 'valid': 10},  # 첫 호출: check_counts=True 시 첫 테이블에서 바로 예외
            {'total': 10, 'valid': 10},  # 두 번째 호출: learning_resources
            {'total': 10, 'valid': 10},  # regulations
            {'total': 10, 'valid': 10},  # knowledge
            {'total': 30, 'valid': 30},  # provenance
        ]), patch.object(vbd.db, 'val', return_value=0):
            # check_counts=True 일 때 시드 개수 불일치 오류
            with self.assertRaisesRegex(ValueError, '시드 데이터 개수 불일치'):
                vbd.verify(check_counts=True)
            # check_counts=False 일 때 정상 통과
            res = vbd.verify(check_counts=False)
            self.assertEqual(res['vectors'], 30)

    def test_knowledge_search_aborts_when_vectors_or_meta_are_incomplete(self):
        # 정상 1건, 누락 1건 (total=2, indexed=1)일 때 에러 발생 검증
        with patch.object(knowledge.db, 'val', return_value='knowledge.chunks'), \
             patch.object(knowledge.db, 'one', return_value={'total': 2, 'indexed': 1}):
            with self.assertRaisesRegex(llm.LlmError, '벡터가 없거나 원문과 달라요'):
                knowledge.search('질문', knowledge.CATEGORIES[1])

    def test_regulation_input_hash_matches_actual_newline_contract(self):
        article = {'path': '취업규칙 > 제1조', 'chunkText': '제1조 본문'}
        expected_text = article['path'] + '\n\n' + article['chunkText']
        expected_sha = hashlib.sha256(expected_text.encode('utf-8')).hexdigest()
        self.assertEqual(regulations.input_text(article), expected_text)
        self.assertEqual(hashlib.sha256(regulations.input_text(article).encode('utf-8')).hexdigest(), expected_sha)

    def test_regulation_reindex_matches_current_sha(self):
        aid = 'chunk_1'
        sample_input = ('취업규칙 > 제1조\n\n제1조 본문', hashlib.sha256('취업규칙 > 제1조\n\n제1조 본문'.encode('utf-8')).hexdigest())
        tx_mock = Mock(spec=regulations.db.Tx)
        tx_mock.all.return_value = [{'rag_chunk_id': aid, 'current_sha': sample_input[1]}]
        tx_mock.run.return_value = None
        with patch.object(regulations, '_inputs', return_value={aid: sample_input}), \
             patch.object(regulations, '_missing', return_value=[aid]), \
             patch.object(regulations.embeddings, 'embed', return_value=[[0.1] * 1024]), \
             patch.object(regulations.embeddings, 'validate', return_value=[[0.1] * 1024]), \
             patch.object(regulations.db, 'tx', return_value=MagicMock(__enter__=Mock(return_value=tx_mock), __exit__=Mock())):
            regulations.ensure_vectors([aid])
            self.assertTrue(tx_mock.all.called)

    def test_regulation_reindex_matches_current_sha(self):
        aid = 'chunk_1'
        sample_input = ('취업규칙 > 제1조\n\n제1조 본문', hashlib.sha256('취업규칙 > 제1조\n\n제1조 본문'.encode('utf-8')).hexdigest())
        tx_mock = Mock(spec=regulations.db.Tx)
        tx_mock.all.return_value = [{'rag_chunk_id': aid, 'current_sha': sample_input[1]}]
        tx_mock.run.return_value = None
        with patch.object(regulations, '_inputs', return_value={aid: sample_input}), \
             patch.object(regulations, '_missing', return_value=[aid]), \
             patch.object(regulations.embeddings, 'embed', return_value=[[0.1] * 1024]), \
             patch.object(regulations.embeddings, 'validate', return_value=[[0.1] * 1024]), \
             patch.object(regulations.db, 'tx', return_value=MagicMock(__enter__=Mock(return_value=tx_mock), __exit__=Mock())):
            regulations.ensure_vectors([aid])
            self.assertTrue(tx_mock.all.called)
