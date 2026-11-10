import unittest
from copy import deepcopy
from unittest.mock import patch
from app.agents.resource_recommendations import candidate_pools,recommend_resources
from app.services.course_recommendations import scope_view,merge_scope,compatible_recommendations

class CourseRecommendationTests(unittest.TestCase):
 def items(self):
  return {str(i):{'id':str(i),'usable':True,'type':'course','skills':['SQL'],'title':'SQL 조회 '+str(i),'curriculum':{'items':[{'title':'SQL 조회 실습'}]},'difficulty':'INTERMEDIATE','cost':100 if i<20 else 0} for i in range(22)}
 def test_free_filter_precedes_candidate_limit_and_ignores_budget(self):
  result=candidate_pools({'goal':'SQL','details':{'budget':999999}},{'skills':[{'name':'SQL'}]},self.items(),limit=2,free_only=True)
  self.assertEqual({r['id'] for r in result[0]['courses']},{'20','21'})
 def test_free_excludes_unknown_course_but_allows_books(self):
  items=self.items();items['20']['cost']=None;items['21']['type']='book';items['21']['cost']=15000
  result=candidate_pools({}, {'skills':[{'name':'SQL'}]},items,free_only=True)[0]
  self.assertEqual(result['courses'],[]);self.assertEqual(result['books'][0]['id'],'21');self.assertEqual(result['books'][0]['cost'],15000)
 def test_paid_courses_still_available_for_other_courses(self):
  result=candidate_pools({}, {'skills':[{'name':'SQL'}]},self.items())[0]
  self.assertTrue(any(r['cost']>0 for r in result['courses']))
 def test_model_receives_selected_course_and_free_candidates_only(self):
  def generate(system,payload):
   self.assertEqual(payload['course']['id'],'A1')
   self.assertTrue(all(r['cost']==0 for r in payload['skills'][0]['courses']))
   return {'skills':[{'name':'SQL','courses':[{'key':'S1-C1','why':'무료','knowledge':'역량'}],'books':[]}]}
  result=recommend_resources({}, {'skills':[{'name':'SQL'}]},self.items(),generate,course={'id':'A1'})
  self.assertEqual(result['skills'][0]['courses'][0]['cost'],0)
 def test_course_cache_isolated_and_global_exclusion_preserved(self):
  base={'generationId':'g','resourceChoices':{'SQL':{'enabled':False}},'courseRecommendations':{'A1':{'recommendations':{'id':'free'},'resourceChoices':{'SQL':{'course':'free','books':[]}}},'A3':{'recommendations':{'id':'paid'}}}}
  view=scope_view(base,'A1');self.assertFalse(view['resourceChoices']['SQL']['enabled']);view['resourceChoices']['SQL']['course']='new'
  saved=merge_scope(base,view)
  self.assertEqual(saved['courseRecommendations']['A3'],base['courseRecommendations']['A3'])
  self.assertEqual(saved['courseRecommendations']['A1']['resourceChoices']['SQL']['course'],'new')
  self.assertIsNone(scope_view(base,'A2')['recommendations'])
 def test_old_cache_only_reuses_valid_saved_choices(self):
  saved={'recommendations':{'skills':[{'name':'SQL','courses':[{'id':'c'}],'books':[]}]},
         'resourceChoices':{'SQL':{'course':'c','books':[],'enabled':True}}}
  with patch('app.catalog.items', return_value={'c':{'type':'course','usable':True}}):
   self.assertIsNotNone(compatible_recommendations(saved,'new'))
   self.assertIsNone(compatible_recommendations(dict(saved,resourceChoices={}), 'new'))
   saved['resourceChoices']['SQL']['course']='unavailable'
   self.assertIsNone(compatible_recommendations(saved, 'new'))

 def test_crash_uses_only_first_three_included_skills(self):
  base={'selection':{'skills':[{'name':n} for n in 'ABCDE']},'skillOrder':list('EDCBA'),'resourceChoices':{n:{'enabled':True} for n in 'ABCDE'}}
  view=scope_view(base,'A2')
  self.assertEqual(view['skillOrder'],list('EDC'))
  self.assertEqual([s['name'] for s in view['selection']['skills']],list('EDC'))
  base['resourceChoices']['D']['enabled']=False
  self.assertEqual(scope_view(base,'A2')['skillOrder'],list('ECB'))
  self.assertEqual(len(scope_view(base,'A3')['selection']['skills']),5)
 def test_model_can_return_only_resource_keys_without_explanations(self):
  result=recommend_resources({}, {'skills':[{'name':'SQL'}]},self.items(),lambda *_:{'skills':[{'name':'SQL','courses':[{'key':'S1-C1'}],'books':[]}]},course={'id':'A1'})
  self.assertEqual(result['skills'][0]['courses'][0]['cost'],0)
