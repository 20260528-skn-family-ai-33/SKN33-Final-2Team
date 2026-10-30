import unittest
from copy import deepcopy
from app.agents.resource_recommendations import candidate_pools,recommend_resources
from app.services.course_recommendations import scope_view,merge_scope,free_cache_valid

class CourseRecommendationTests(unittest.TestCase):
 def items(self):
  return {str(i):{'id':str(i),'usable':True,'type':'course','skills':['S'],'title':str(i),'cost':100 if i<20 else 0} for i in range(22)}
 def test_free_filter_precedes_candidate_limit_and_ignores_budget(self):
  result=candidate_pools({'goal':'S','details':{'budget':999999}},{'skills':[{'name':'S'}]},self.items(),limit=2,free_only=True)
  self.assertEqual({r['id'] for r in result[0]['courses']},{'20','21'})
 def test_free_excludes_unknown_cost_for_courses_and_books(self):
  items=self.items();items['20']['cost']=None;items['21']['type']='book'
  result=candidate_pools({}, {'skills':[{'name':'S'}]},items,free_only=True)[0]
  self.assertEqual(result['courses'],[]);self.assertEqual(result['books'][0]['id'],'21')
 def test_paid_courses_still_available_for_other_courses(self):
  result=candidate_pools({}, {'skills':[{'name':'S'}]},self.items())[0]
  self.assertTrue(any(r['cost']>0 for r in result['courses']))
 def test_model_receives_selected_course_and_free_candidates_only(self):
  def generate(system,payload):
   self.assertEqual(payload['course']['id'],'A1')
   self.assertTrue(all(r['cost']==0 for r in payload['skills'][0]['courses']))
   return {'skills':[{'name':'S','courses':[{'key':'S1-C1','why':'무료','knowledge':'역량'}],'books':[]}]}
  result=recommend_resources({}, {'skills':[{'name':'S'}]},self.items(),generate,course={'id':'A1'})
  self.assertEqual(result['skills'][0]['courses'][0]['cost'],0)
 def test_course_cache_isolated_and_global_exclusion_preserved(self):
  base={'generationId':'g','resourceChoices':{'S':{'enabled':False}},'courseRecommendations':{'A1':{'recommendations':{'id':'free'},'resourceChoices':{'S':{'course':'free','books':[]}}},'A3':{'recommendations':{'id':'paid'}}}}
  view=scope_view(base,'A1');self.assertFalse(view['resourceChoices']['S']['enabled']);view['resourceChoices']['S']['course']='new'
  saved=merge_scope(base,view)
  self.assertEqual(saved['courseRecommendations']['A3'],base['courseRecommendations']['A3'])
  self.assertEqual(saved['courseRecommendations']['A1']['resourceChoices']['S']['course'],'new')
  self.assertIsNone(scope_view(base,'A2')['recommendations'])
 def test_free_cache_invalidated_if_latest_price_changes(self):
  rec={'skills':[{'courses':[{'id':'c','cost':0}],'books':[]}]}
  self.assertTrue(free_cache_valid(rec,{'c':{'cost':0,'usable':True}}))
  for cost in (None,100):self.assertFalse(free_cache_valid(rec,{'c':{'cost':cost,'usable':True}}))

 def test_crash_uses_only_first_three_included_skills(self):
  base={'selection':{'skills':[{'name':n} for n in 'ABCDE']},'skillOrder':list('EDCBA'),'resourceChoices':{n:{'enabled':True} for n in 'ABCDE'}}
  view=scope_view(base,'A2')
  self.assertEqual(view['skillOrder'],list('EDC'))
  self.assertEqual([s['name'] for s in view['selection']['skills']],list('EDC'))
  base['resourceChoices']['D']['enabled']=False
  self.assertEqual(scope_view(base,'A2')['skillOrder'],list('ECB'))
  self.assertEqual(len(scope_view(base,'A3')['selection']['skills']),5)
 def test_model_can_return_only_resource_keys_without_explanations(self):
  result=recommend_resources({}, {'skills':[{'name':'S'}]},self.items(),lambda *_:{'skills':[{'name':'S','courses':[{'key':'S1-C1'}],'books':[]}]},course={'id':'A1'})
  self.assertEqual(result['skills'][0]['courses'][0]['cost'],0)
