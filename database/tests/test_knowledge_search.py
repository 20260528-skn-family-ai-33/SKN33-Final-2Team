"""Behavior checks for frozen-chunk hybrid search; no paid requests."""
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from src.database.ingestion.knowledge_search import rank_records, inferred_site, lexical_scores, hybrid_search_vector
from src.database.ingestion.knowledge_documents import search


def row(identity, text, similarity=0.8, site='본사', category='사내 생활안내'):
    return {'chunk_id':identity,'chunk_text':text,'similarity':similarity,'category':category,
            'is_virtual':True,'metadata':{'site':site,'section_title':''}}


class KnowledgeSearchTests(unittest.TestCase):
    def test_place_filters_exclude_other_site_and_keep_shared_guide(self):
        data=[row('hq','본사 식당',0.99),row('hrd','인재개발원 식당',0.8,'인재개발원'),
              row('both','양쪽 시설 안내',0.7,'본사·인재개발원')]
        hits=rank_records(data,'교육원 식당 위치',category='사내 생활안내')
        self.assertEqual({r['chunk_id'] for r in hits},{'hrd','both'})
        self.assertTrue(all(r['site_filter']=='인재개발원' for r in hits))

    def test_comparing_both_places_or_unspecified_place_does_not_force_hq(self):
        self.assertIsNone(inferred_site('본사와 교육원 식당 비교','사내 생활안내'))
        self.assertIsNone(inferred_site('식당 위치','사내 생활안내'))
        self.assertIsNone(inferred_site('본사 주소','수자원공사 정보'))

    def test_keyword_signal_handles_korean_particles_without_gold_metadata(self):
        rows=[row('actual','기관 형태는 준시장형 공기업입니다.',category='수자원공사 정보'),
              row('other','물관리 주요사업 소개입니다.',category='수자원공사 정보')]
        scores=lexical_scores(rows,'준시장형 공기업이라고 되어 있나요?')
        self.assertGreater(scores['actual'],scores.get('other',0))
        hits=rank_records(rows,'준시장형 공기업이라고 되어 있나요?',category='수자원공사 정보')
        self.assertEqual(hits[0]['chunk_id'],'actual')

    def test_fusion_adds_keyword_candidate_outside_vector_pool(self):
        data=[row(f'generic-{i:02d}','일반 시설 안내',0.99-i*0.01) for i in range(21)]
        data.append(row('exact','희귀설비 수리 접수 경로',0.5))
        hits=rank_records(data,'희귀설비 수리 접수',category='사내 생활안내')
        self.assertIn('exact',{r['chunk_id'] for r in hits})
        exact=next(r for r in hits if r['chunk_id']=='exact')
        self.assertIsNone(exact['vector_rank'])
        self.assertEqual(exact['lexical_rank'],1)

    def test_cosine_threshold_still_applies_to_keyword_candidates(self):
        hits=rank_records([row('exact','희귀설비',0.24)],'희귀설비',category='사내 생활안내')
        self.assertEqual(hits,[])

    def test_unknown_words_empty_rows_and_deterministic_order(self):
        self.assertEqual(rank_records([],'문의',category='사내 생활안내'),[])
        data=[row('b','시설 안내'),row('a','시설 안내')]
        self.assertEqual([r['chunk_id'] for r in rank_records(data,'zzqx',category='사내 생활안내')],['a','b'])

    def test_cache_content_signature_refreshes_after_text_changes(self):
        before=[row('x','희귀설비'),row('y','다른 공간')]
        after=[row('x','다른 공간'),row('y','희귀설비')]
        self.assertGreater(lexical_scores(before,'희귀설비').get('x',0),lexical_scores(before,'희귀설비').get('y',0))
        self.assertGreater(lexical_scores(after,'희귀설비').get('y',0),lexical_scores(after,'희귀설비').get('x',0))

    def test_categories_never_leak_and_provenance_survives(self):
        rows=[row('guide','희귀설비',0.8),row('company','희귀설비',0.99,category='수자원공사 정보')]
        found=rank_records(rows,'희귀설비',category='사내 생활안내')
        self.assertEqual([r['chunk_id'] for r in found],['guide'])
        self.assertTrue(found[0]['is_virtual'])
        self.assertEqual(found[0]['metadata'],rows[0]['metadata'])
        self.assertEqual(found[0]['chunk_text'],rows[0]['chunk_text'])

    def test_invalid_inputs_do_not_touch_database(self):
        conn=MagicMock()
        for kwargs in ({'query':'','category':'사내 생활안내'}, {'query':'문의','category':'규정'},
                       {'query':'문의','category':'사내 생활안내','limit':0}):
            with self.assertRaises(ValueError):hybrid_search_vector(conn,[1.0]+[0.0]*1535,**kwargs)
        conn.execute.assert_not_called()

    def test_public_search_embeds_once_and_passes_question_to_hybrid(self):
        conn,client=MagicMock(),MagicMock()
        response=SimpleNamespace(model='text-embedding-3-small',data=[SimpleNamespace(index=0,embedding=[1.0]+[0.0]*1535)])
        client.embeddings.create.return_value=response
        with patch('src.database.ingestion.knowledge_search.hybrid_search_vector',return_value=[{'chunk_id':'x'}]) as hybrid:
            result=search(conn,'교육원 식당 위치',category='사내 생활안내',client=client)
        self.assertEqual(result,[{'chunk_id':'x'}])
        self.assertEqual(client.embeddings.create.call_count,1)
        self.assertEqual(hybrid.call_args.kwargs['query'],'교육원 식당 위치')


if __name__=='__main__':unittest.main()
