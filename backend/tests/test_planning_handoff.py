import unittest
from app.services.planning_handoff import build_handoff

class PlanningHandoffTests(unittest.TestCase):
 def saved(self):
  return {'completed':True,'generationId':'new','project':{'goal':'분석','projectSummary':'요약'},'selection':{'skills':[]},'survey':{'groups':[]},'answers':{},'recommendations':{'skills':[{'name':n,'courses':[],'books':[]} for n in ['A','B']]},'skillOrder':['B','A'],'resourceChoices':{n:{'course':None,'books':[],'enabled':True} for n in ['A','B']}}
 def test_new_assessment_without_legacy_diagnosis_passes(self):
  h=build_handoff(self.saved(),{},{});self.assertEqual(h['focus'],['B','A']);self.assertEqual(h['projectSummary'],'요약')
 def test_excluded_skills_are_not_passed_as_focus(self):
  s=self.saved();s['resourceChoices']['A']['enabled']=False
  h=build_handoff(s,{},{});self.assertEqual(h['focus'],['B']);self.assertEqual(h['excludedSkills'],['A'])
 def test_input_change_invalidates_generated_option_key(self):
  s=self.saved();old=build_handoff(s,{},{})['key'];s['skillOrder'].reverse();self.assertNotEqual(old,build_handoff(s,{},{})['key'])
 def test_incomplete_or_all_excluded_rejected(self):
  s=self.saved();s['completed']=False
  with self.assertRaises(ValueError):build_handoff(s,{},{})
  s=self.saved()
  for c in s['resourceChoices'].values():c['enabled']=False
  with self.assertRaises(ValueError):build_handoff(s,{},{})
