from copy import deepcopy
import unittest
from app.services.course_recommendations import (scope_view,merge_scope,option_cache_key,
    invalidate_course_tail,archive_course_cache,dependency_key,prune_course_versions)

class CourseMaterialVersionTests(unittest.TestCase):
 def option(self,version):
  return {'id':'A1','optionId':version,'learningSkillsVersion':'skills','learningSkills':[{'name':'SQL','application':'분석'}]}
 def save(self,base,option,book):
  view=scope_view(base,'A1',option)
  view.update(recommendations={'id':'rec-'+book,'skills':[]},resourceChoices={'SQL':{'course':'course-'+book,'books':[book],'enabled':True}},durationEstimates={'SQL':{'weeks':2}},materialsSelectionKey='selection-'+book,activityProposal={'id':'task-'+book},activityVersions=[{'id':'task-'+book}],learningOutcomes={'summaries':{'SQL':[book]}})
  return merge_scope(base,view)
 def test_roundtrip_preserves_each_versions_materials_choices_and_other_course(self):
  old,new=self.option('old'),self.option('new')
  base=self.save({'generationId':'g'},old,'old-book')
  base['courseRecommendations']['A3']={'marker':'keep'}
  w={'draft':{'chosen':'A1','gen':{'options':{'A1':old}}},'v2Survey':base,'draftPlan':{'opt':'A1'}}
  invalidate_course_tail(w,'A1');w['draft']['gen']['options']['A1']=new
  self.assertIsNone(scope_view(w['v2Survey'],'A1',new)['recommendations'])
  w['v2Survey']=self.save(w['v2Survey'],new,'new-book')
  invalidate_course_tail(w,'A1');w['draft']['gen']['options']['A1']=old
  restored=scope_view(w['v2Survey'],'A1',old)
  self.assertEqual(restored['resourceChoices']['SQL']['books'],['old-book'])
  self.assertEqual(restored['recommendations']['id'],'rec-old-book')
  self.assertEqual(restored['activityProposal']['id'],'task-old-book')
  restored['resourceChoices']['SQL']['books']=[]
  w['v2Survey']=merge_scope(w['v2Survey'],restored)
  invalidate_course_tail(w,'A1');w['draft']['gen']['options']['A1']=new
  self.assertEqual(scope_view(w['v2Survey'],'A1',new)['resourceChoices']['SQL']['books'],['new-book'])
  self.assertEqual(scope_view(w['v2Survey'],'A1',old)['resourceChoices']['SQL']['books'],[])
  self.assertEqual(w['v2Survey']['courseRecommendations']['A3'],{'marker':'keep'})
 def test_support_changes_do_not_change_version_or_selection(self):
  old=self.option('old');base=self.save({},old,'book')
  supported=dict(deepcopy(old),support={'text':'ready'},supportFail={'message':'failed'})
  self.assertEqual(option_cache_key(old),option_cache_key(supported))
  self.assertEqual(scope_view(base,'A1',supported)['recommendations']['id'],'rec-book')
 def test_legacy_cache_is_assigned_before_switch_without_data_loss(self):
  old,new=self.option('old'),self.option('new')
  base=self.save({},old,'book');base.pop('courseRecommendationVersions');base['courseRecommendations']['A1'].pop('optionKey')
  w={'draft':{'chosen':'A1','gen':{'options':{'A1':old}}},'v2Survey':base}
  archive_course_cache(w,'A1');w['draft']['gen']['options']['A1']=new;invalidate_course_tail(w,'A1')
  self.assertIsNone(scope_view(base,'A1',new)['recommendations'])
  self.assertEqual(scope_view(base,'A1',old)['recommendations']['id'],'rec-book')
 def test_late_generation_from_another_version_has_different_dependency(self):
  base={'generationId':'g'}
  self.assertNotEqual(dependency_key(scope_view(base,'A1',self.option('old'))),dependency_key(scope_view(base,'A1',self.option('new'))))
 def test_pruning_removes_only_versions_no_longer_in_history(self):
  options=[self.option(str(i)) for i in range(7)]
  base={}
  for i,option in enumerate(options):base=self.save(base,option,str(i))
  retained=[options[0]]+options[2:]
  w={'draft':{'gen':{'options':{'A1':options[-1]},'hist':{'A1':retained}}},'v2Survey':base}
  prune_course_versions(w,'A1')
  self.assertEqual(set(base['courseRecommendationVersions']['A1']),{option_cache_key(o) for o in retained})
