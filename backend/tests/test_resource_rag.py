import unittest
from unittest.mock import Mock,patch
from app.services.resource_rag import retrieve,query_text,validate_vectors,cached_vectors,search_vectors,DIMENSIONS,MODEL,VERSION
from app.agents.resource_recommendations import RecommendationError

VECTOR=[1.0]+[0.0]*(DIMENSIONS-1)
class ResourceRagTests(unittest.TestCase):
 def setUp(self):
  cached_vectors.cache_clear()
  self.project={'goal':'자료 분석','projectSummary':'프로젝트 요약','desiredCompetencies':'분석 역량'}
  self.selection={'skills':[{'name':'S','application':'실무 적용'}]}
  self.items={str(i):{'id':str(i),'type':'course','usable':True,'skills':['S'],'title':str(i),'cost':0 if i>=20 else 100} for i in range(25)}
 def embed(self,texts):return [VECTOR for _ in texts]
 def search(self,kind,ids,vector,limit,free):
  return [{'resource_id':rid,'similarity':.7,'current_cost':self.items[rid]['cost']} for rid in ids[:limit]]
 def test_free_filters_before_search_and_limit(self):
  search=Mock(side_effect=self.search)
  pools,meta=retrieve(self.project,self.selection,self.items,{'id':'A1'},embed=self.embed,search=search)
  self.assertEqual(set(search.call_args.args[1]),{'20','21','22','23','24'})
  self.assertTrue(search.call_args.args[4]);self.assertTrue(all(r['cost']==0 for r in pools[0]['courses']))
  self.assertEqual(meta['version'],VERSION)
 def test_project_skill_and_course_all_reach_embedding_input(self):
  text=query_text(self.project,self.selection['skills'][0],{'id':'A2','scope':'단기 실습'})
  for expected in ['프로젝트 요약','분석 역량','실무 적용','A2','단기 실습']:self.assertIn(expected,text)
 def test_all_skill_queries_batched_once(self):
  selection={'skills':[{'name':'S'},{'name':'T'}]};items=dict(self.items,t={'id':'t','type':'course','usable':True,'skills':['T'],'cost':0})
  embed=Mock(side_effect=self.embed)
  retrieve(self.project,selection,items,embed=embed,search=lambda kind,ids,*args:[{'resource_id':ids[0],'similarity':.5,'current_cost':0}])
  embed.assert_called_once();self.assertEqual(len(embed.call_args.args[0]),2)
 def test_vector_order_preserved_and_max_six_per_kind(self):
  search=lambda kind,ids,*args:[{'resource_id':rid,'similarity':.5,'current_cost':0} for rid in sorted(ids,key=int,reverse=True)]
  pools,_=retrieve(self.project,self.selection,self.items,embed=self.embed,search=search)
  self.assertEqual(len(pools[0]['courses']),6)
  self.assertEqual(pools[0]['courses'][0]['id'],list(reversed(list(self.items)))[0])
 def test_missing_vector_does_not_fallback_to_keywords(self):
  with self.assertRaises(RecommendationError):retrieve(self.project,self.selection,self.items,embed=self.embed,search=lambda *_:[])
 def test_unknown_resource_and_paid_free_result_rejected(self):
  for row in [{'resource_id':'outside','similarity':.5,'current_cost':0},{'resource_id':'20','similarity':.5,'current_cost':100}]:
   with self.subTest(row=row),self.assertRaises(RecommendationError):retrieve(self.project,self.selection,self.items,{'id':'A1'},embed=self.embed,search=lambda *_:[row])
 def test_empty_candidates_do_not_call_embedding(self):
  embed=Mock();pools,_=retrieve(self.project,self.selection,{},embed=embed);embed.assert_not_called();self.assertEqual(pools[0]['courses'],[])
 def test_wrong_dimensions_nonfinite_zero_and_count_rejected(self):
  for vectors in ([[1.0]],[[0.0]*DIMENSIONS],[[float('nan')]+VECTOR[1:]],[],[[True]+VECTOR[1:]]):
   with self.subTest(vectors=len(vectors)),self.assertRaises(RecommendationError):validate_vectors(vectors,1)
 def test_embedding_cache_reuses_same_query_without_db_writes(self):
  with patch('app.services.resource_rag.llm.embed_model',return_value=MODEL),patch('app.services.resource_rag.llm.embed_ready',return_value=True),patch('app.services.resource_rag.llm.embed',return_value=[VECTOR]) as embed:
   cached_vectors(('query',));cached_vectors(('query',));embed.assert_called_once()
 def test_sql_only_reads_and_filters_before_limit(self):
  with patch('app.services.resource_rag.db.all_',return_value=[]) as query:
   search_vectors('courses',['20'],VECTOR,6,True)
   sql=query.call_args.args[0].upper();self.assertTrue(sql.strip().startswith('SELECT'))
   self.assertNotIn('INSERT',sql);self.assertNotIn('UPDATE ',sql);self.assertLess(sql.index('M.COST_WON=0'),sql.index('LIMIT'))
   self.assertEqual(query.call_args.kwargs['model'],MODEL)
