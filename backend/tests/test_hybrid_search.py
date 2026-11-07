"""BM25 수식·독립 후보 합집합·RRF·검색 경계·부모 조항 문맥을 외부 연결 없이 확인한다."""
from __future__ import annotations

import math
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app import bge_knowledge_search as knowledge, bge_regulation_search as regulation, config, hybrid_search as hybrid, llm, regstore

VECTOR = [1.0] + [0.0] * 1023


class HybridMathTest(unittest.TestCase):
    def test_bm25_matches_known_term_frequency_length_and_idf_formula(self):
        # 세 문서, 평균 길이 2, a의 df=2. 문서 x의 tf=2·길이=3.
        hits = hybrid.bm25('a', [('x', 'a a b'), ('y', 'a b'), ('z', 'c')])
        expected = math.log1p(1.5 / 2.5) * 2 * 2.2 / (2 + 1.2 * (.25 + .75 * 3 / 2))
        self.assertEqual(hits[0]['id'], 'x')
        self.assertAlmostEqual(hits[0]['score'], expected)

    def test_korean_particles_spacing_and_english_case(self):
        documents = [('leave', '연차휴가와 제33조의4의 기준'), ('code', 'API K-WATER'), ('other', '교육 신청')]
        self.assertEqual(hybrid.bm25('연차휴가는', documents)[0]['id'], 'leave')
        self.assertIn('word:제33조의4', hybrid.tokenize('제 33 조 의 4'))
        self.assertIn('law:제33조의4', hybrid.tokenize('제33조의4의 기준'))
        self.assertIn('word:1.5', hybrid.tokenize('1.5'))
        self.assertEqual(hybrid.bm25('api k-water', documents)[0]['id'], 'code')

    def test_empty_and_unmatched_query_return_no_keyword_hits(self):
        for question in ('', '!!!', 'unknown'):
            self.assertEqual(hybrid.bm25(question, [('a', 'known')]), [])
        self.assertEqual(hybrid.bm25('known', []), [])

    def test_keyword_cache_tracks_text_membership_and_deletions(self):
        hybrid._index.cache_clear()
        self.assertTrue(hybrid.bm25('leave', [('a', 'leave')]))
        self.assertFalse(hybrid.bm25('leave', [('a', 'salary')]))
        self.assertEqual(hybrid.bm25('leave', [('b', 'leave')])[0]['id'], 'b')
        self.assertFalse(hybrid.bm25('leave', []))

    def test_rrf_sums_ranks_not_incompatible_scores(self):
        vector = [{'id': 'v', 'score': .99}, {'id': 'both', 'score': .2}]
        keywords = [{'id': 'b', 'score': 1000}, {'id': 'both', 'score': 800}]
        hits = hybrid.fuse(vector, keywords, 3)
        self.assertEqual(hits[0]['id'], 'both')
        self.assertAlmostEqual(hits[0]['rrfScore'], 2 / 62)
        self.assertEqual(hits[0]['vectorScore'], .2)
        self.assertEqual(hits[0]['bm25Score'], 800)
        self.assertEqual({hit['id'] for hit in hits}, {'v', 'b', 'both'})

    def test_rrf_duplicates_count_only_once_and_ties_are_stable(self):
        self.assertAlmostEqual(hybrid.fuse([{'id': 'a', 'score': 1}] * 2, [], 1)[0]['rrfScore'], 1 / 61)
        hits = hybrid.fuse([{'id': 'z', 'score': 1}], [{'id': 'a', 'score': 10}], 2)
        self.assertEqual([hit['id'] for hit in hits], ['a', 'z'])
        self.assertEqual(hybrid.fuse([], [], 2), [])

    def test_invalid_limit_and_duplicate_corpus_are_rejected(self):
        with self.assertRaises(ValueError):
            hybrid.bm25('a', [('x', 'a'), ('x', 'b')])
        with self.assertRaises(ValueError):
            hybrid.bm25('a', [], 0)
        with self.assertRaises(ValueError):
            hybrid.fuse([], [], 0)

    def test_default_hybrid_and_invalid_config(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(config, '_FILE', {}):
            self.assertTrue(hybrid.enabled())
        with patch.dict(os.environ, ASSISTANT_SEARCH_MODE='typo'):
            with self.assertRaisesRegex(llm.LlmError, 'ASSISTANT_SEARCH_MODE'):
                hybrid.enabled()


class HybridRetrievalTest(unittest.TestCase):
    def setUp(self):
        settings = patch.dict(os.environ, ASSISTANT_SEARCH_MODE='hybrid')
        settings.start()
        self.addCleanup(settings.stop)

    def test_regulations_include_keyword_hit_outside_vector_candidates_and_group_parent(self):
        articles = {key: {'id': key, 'reg': 'r', 'node': key, 'parent': 'p' if key.startswith('p') else None}
                    for key in ('p1', 'p2', 'keyword')}
        inputs = {'p1': ('별도 문서', 'sha'), 'p2': ('별도 문서', 'sha'), 'keyword': ('재택근무 장소이탈', 'sha')}
        with patch.object(regstore, 'pool', return_value=list(articles.values())), patch.object(regstore, 'article', side_effect=articles.get), patch.object(regulation, '_inputs', return_value=inputs), patch.object(regulation, '_missing', return_value=[]), patch.object(regulation, '_stored', return_value={}), patch.object(regulation.embeddings, 'embed', return_value=[VECTOR]), patch.object(regulation.db, 'all_', return_value=[{'rag_chunk_id': 'p1', 'score': .9}, {'rag_chunk_id': 'p2', 'score': .8}]) as sql:
            hits = regulation.search('장소이탈', 5, '일반직')
        self.assertEqual({hit['id'] for hit in hits}, {'p1', 'keyword'})
        lexical = next(hit for hit in hits if hit['id'] == 'keyword')
        self.assertIsNone(lexical['vectorRank'])
        self.assertEqual(lexical['bm25Rank'], 1)
        self.assertEqual(sql.call_args.kwargs['i'], list(articles))
        self.assertEqual(sql.call_args.kwargs['k'], 50)

    def test_knowledge_bm25_sees_full_allowed_corpus_and_keeps_provenance(self):
        for category, real_only in zip(knowledge.CATEGORIES, (True, False)):
            def row(identifier, text):
                return {'chunk_id': identifier, 'chunk_text': text, 'document_title': '원문',
                        'category': category, 'is_virtual': not real_only, 'metadata': {'location': '1절'}}
            dense = dict(row('dense', '다른 내용'), similarity=.8)
            lexical = row('lexical', '주차출입증 신청')
            with self.subTest(category=category), patch.object(knowledge.db, 'val', return_value=knowledge.TABLE), patch.object(knowledge.db, 'one', return_value={'total': 2, 'indexed': 2}), patch.object(knowledge.embeddings, 'embed', return_value=[VECTOR]), patch.object(knowledge.db, 'all_', side_effect=[[dense], [dense, lexical]]) as sql, patch.object(knowledge.db, 'tx') as writes:
                hits = knowledge.search('주차출입증', category)
            hit = next(hit for hit in hits if hit['chunk_id'] == 'lexical')
            self.assertEqual(hit['metadata'], {'location': '1절'})
            self.assertIsNone(hit['similarity'])
            self.assertIsNone(hit['retrieval']['vectorRank'])
            self.assertEqual(hit['is_virtual'], not real_only)
            for call in sql.call_args_list:
                self.assertEqual(call.kwargs['category'], category)
                self.assertEqual(call.kwargs['real_only'], real_only)
                self.assertIn('v.input_sha256=c.chunk_text_sha256', call.args[0])
            self.assertEqual(sql.call_args_list[0].kwargs['limit'], 50)
            writes.assert_not_called()

    def test_explicit_reference_precedes_other_articles_mentioning_same_number(self):
        articles = {key: {'id': key, 'reg': 'work', 'node': key} for key in ('exact', 'citing')}
        inputs = {key: ('취업규칙 제33조의4를 따른다', 'sha') for key in articles}
        with patch.object(regstore, 'pool', return_value=list(articles.values())), patch.object(regstore, 'article', side_effect=articles.get), patch.object(regstore, 'explicit_ref', return_value={'ids': ['exact', 'outside-scope']}), patch.object(regulation, '_inputs', return_value=inputs), patch.object(regulation, '_missing', return_value=[]), patch.object(regulation, '_stored', return_value={}), patch.object(regulation.embeddings, 'embed', return_value=[VECTOR]), patch.object(regulation.db, 'all_', return_value=[{'rag_chunk_id': 'citing', 'score': .9}]):
            hits = regulation.search('취업규칙 제33조의4', 5, '일반직')
        self.assertEqual(hits[0]['id'], 'exact')
        self.assertTrue(hits[0]['exactReference'])
        self.assertNotIn('outside-scope', [hit['id'] for hit in hits])

    def test_dense_failure_is_not_silently_converted_to_keyword_only(self):
        with patch.object(knowledge.db, 'val', return_value=knowledge.TABLE), patch.object(knowledge.db, 'one', return_value={'total': 1, 'indexed': 1}), patch.object(knowledge.embeddings, 'embed', side_effect=llm.LlmError('BGE-M3 연결 실패')), patch.object(hybrid, 'bm25') as keywords:
            with self.assertRaises(llm.LlmError):
                knowledge.search('질문', knowledge.CATEGORIES[0])
        keywords.assert_not_called()

    def test_parent_context_keeps_actual_parent_group_and_limit(self):
        def article(identifier, **extra):
            return dict(id=identifier, reg='r', parent='p', group='일반직', overseas=False,
                        type='paragraph', path='', order=1, **extra)
        allowed = [article('hit'), article('sibling'), dict(article('wrong-parent'), parent='other'),
                   dict(article('wrong-reg'), reg='other'), dict(article('other-group'), group='실무직'),
                   dict(article('overseas'), overseas=True), dict(article('no-parent'), parent=None)]
        with patch.object(regstore, 'data', return_value={'arts': {item['id']: item for item in allowed}}):
            self.assertEqual(regstore.parent_context(['hit'], '일반직', '휴가', limit=2), ['sibling'])
            self.assertEqual(regstore.parent_context(['hit'], '일반직', '국외근무', limit=1), ['overseas'])
            self.assertEqual(regstore.parent_context(['hit'], '일반직', '휴가', limit=0), [])
            self.assertEqual(regstore.parent_context(['no-parent'], '일반직', '휴가', limit=2), [])


if __name__ == '__main__':
    unittest.main()
