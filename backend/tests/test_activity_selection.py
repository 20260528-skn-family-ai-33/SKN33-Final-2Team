import unittest
from copy import deepcopy
from unittest.mock import patch
from app.errors import ApiError
from app.services.activity_selection import propose,current_record,selection_option

class ActivityTests(unittest.TestCase):
 def setUp(self):
  self.saved={'completed':True,'generationId':'g','recommendations':{'id':'r'},'resourceChoices':{'S':{'course':'c','books':[]}},'skillOrder':['S'],'project':{'goal':'goal'}}
  self.draft={'chosen':'A2','handoff':{'key':'h'},'gen':{'options':{'A2':{'id':'A2'}}}}
  self.acts=[{'skill':'S','stage':2,'title':'학습','res':'c','hours':2,'how':'학습 후 확인한다.'},{'skill':'S','stage':3,'title':'적용','res':None,'hours':2,'how':'구현 후 확인한다.'}]
 def propose(self,acts=None,cost=0):
  with patch('app.services.activity_selection.catalog.items',return_value={'c':{'id':'c','title':'자료','cost':cost}}),patch('app.services.activity_selection.RM.finish_option',side_effect=lambda pid,raw,source:{**raw,'acts':[dict(a,id=str(i)) for i,a in enumerate(raw['acts'])]}):
   return propose(self.saved,self.draft,lambda *_:{'acts':self.acts if acts is None else acts},'openai')
 def test_all_proposed_activities_selected_by_default(self):
  p=self.propose();self.assertEqual(p['selectedIds'],['0','1'])
 def test_unselected_material_rejected(self):
  acts=deepcopy(self.acts);acts[0]['res']='outside'
  with self.assertRaises(ApiError):self.propose(acts)
 def test_missing_selected_material_rejected(self):
  with self.assertRaises(ApiError):self.propose(self.acts[1:])
 def test_excluded_skill_rejected(self):
  acts=deepcopy(self.acts);acts[0]['skill']='other'
  with self.assertRaises(ApiError):self.propose(acts)
 def test_selection_keeps_only_selected_activity(self):
  self.saved['activityProposal']=self.propose()
  self.assertEqual(len(selection_option(self.saved,self.draft,['1'])['acts']),1)
  with self.assertRaises(ApiError):selection_option(self.saved,self.draft,[])
 def test_changed_materials_invalidate_activity_proposal(self):
  self.saved['activityProposal']=self.propose();self.saved['resourceChoices']['S']['books']=['new']
  self.assertIsNone(current_record(self.saved,self.draft))
 def test_free_course_rejects_paid_material(self):
  self.draft['chosen']='A1';self.draft['gen']['options']['A1']={'id':'A1'}
  with self.assertRaises(ApiError):self.propose(cost=100)
