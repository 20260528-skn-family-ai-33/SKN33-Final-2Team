"""수정 지점부터 확정까지의 의존성·늦은 결과 차단을 한 흐름으로 검증한다."""
import copy,json,unittest
from contextlib import nullcontext
from unittest.mock import Mock,patch
from uuid import uuid4
from fastapi.testclient import TestClient
from app.services import drafts,course_skills,survey_store,activity_selection
from app.services.course_recommendations import scope_view,merge_scope
from app.routers import preassessment as api
from app.auth import Account,require_employee
from app.errors import ApiError
from test_preassessment_api import api_app

class FlowCompatibilityTests(unittest.TestCase):
 def state(self):
  option={'id':'A1','name':'Free','short':'기초','tagline':'목표','pros':[],'cons':[],
   'learningSkillsVersion':'v1','learningSkills':[{'name':'S','application':'검색 구성'}],'acts':[]}
  option['learningSkillsKey']=course_skills.recommendation_key(option)
  d=drafts.fresh_draft();d.update(goal='검색 구현',detailsOk=True,chosen='A1',handoff={'key':'h','startStage':1,'prefs':{'weeklyHours':4}},gen={'key':'h','options':{'A1':option,'A3':dict(option,id='A3')}})
  base={'version':1,'generationId':'g','completed':True,'project':{'goal':'검색 구현','details':{'hours':4}},'selection':{'skills':[{'name':'S'}]},'survey':{'groups':[]},'answers':{'q':0}}
  scoped=scope_view(base,'A1',option)
  scoped.update(recommendations={'id':'r','skills':[{'name':'S','courses':[{'id':'c','title':'강좌','hours':8}],'books':[{'id':'b','title':'도서'}]}]},resourceChoices={'S':{'course':'c','books':['b'],'enabled':True}},durationEstimates={'S':{'weeks':3,'course':'c','books':['b']}})
  scoped['materialsSelectionKey']=activity_selection.materials_key(scoped)
  record={'id':'proposal','key':activity_selection.fingerprint(scoped,d),'selectedIds':['task'],
   'skillSummaries':{'S':['검색 구성','검색 평가','결과 검증']},'option':dict(option,acts=[{'id':'task','skill':'S','stage':3,'title':'과제','res':None,'hours':20,'how':'설명'}])}
  scoped['activityProposal']=record;scoped['activityVersions']=[record];scoped['learningOutcomes']={'key':record['key'],'summaries':record['skillSummaries']}
  base=merge_scope(base,scoped);base['courseRecommendations']['A3']={'marker':'보존'}
  return {'gp5':1,'draft':d,'v2Survey':base,'draftPlan':{'opt':'A1','marker':'이전 검토 결과'}},scoped

 def test_goal_or_conditions_edit_clears_every_downstream_stage(self):
  for change in ({'goal':'바꾼 목표'},{'prefs':{'hours':8}}):
   with self.subTest(change=change):
    w,_=self.state();drafts._apply_client(w,change)
    self.assertNotIn('v2Survey',w)
    for key in ('quiz','diag','handoff','gen','chosen'):self.assertIsNone(w['draft'][key])
    self.assertIsNone(w['draftPlan'])

 def test_switching_plan_version_discards_all_its_material_and_task_caches(self):
  w,_=self.state();g=w['draft']['gen'];old=g['options']['A1'];new=copy.deepcopy(old);new['learningSkillsVersion']='v2'
  g.update(hist={'A1':[old,new]},cur={'A1':0})
  drafts._apply_client(w,{'genCur':{'A1':1}})
  self.assertNotIn('A1',w['v2Survey']['courseRecommendations']);self.assertIsNone(w['draftPlan'])
  self.assertEqual(w['v2Survey']['courseRecommendations']['A3'],{'marker':'보존'})
  drafts._apply_client(w,{'genCur':{'A1':0}})
  self.assertIsNone(scope_view(w['v2Survey'],'A1',old)['recommendations'])

 def test_material_edit_clears_all_tasks_versions_outcomes_and_old_review(self):
  w,scoped=self.state();t=Mock();t.one.return_value={'draft_choices':w};t.run.return_value=1
  choices={'S':{'course':'c','books':[],'enabled':True}}
  result=survey_store.save_resource_choices(t,1,'p','g','r',choices,skill_order=['S'],course='A1')
  for field in ('activityProposal','activityVersions','learningOutcomes'):self.assertFalse(result.get(field))
  self.assertTrue(activity_selection.materials_ready(result));self.assertEqual(result['durationEstimates']['S']['weeks'],2)
  self.assertIn("'{draftPlan}'",t.run.call_args.args[0])
  self.assertEqual(json.loads(t.run.call_args.kwargs['draft'])['chosen'],'A1')

 def test_confirmed_report_keeps_selected_resources_and_combined_outcomes(self):
  w,scoped=self.state();d=w['draft']
  option=activity_selection.selection_option(scoped,d,['task'])
  plan=drafts.RM.build_plan(option,{'hours':4},d['goal'])
  self.assertEqual(plan['weeks'],3)
  report=plan['def']['learningReport']
  self.assertEqual(report['recommendations']['skills'][0]['courses'][0]['id'],'c')
  self.assertEqual(report['skillDetails'][0]['competencySummary'],['검색 구성','검색 평가','결과 검증'])
  self.assertEqual(plan['acts'][0]['skill'],'S')

 def test_stale_review_cannot_be_confirmed_after_material_change(self):
  w,scoped=self.state();scoped['resourceChoices']['S']['books']=[];t=Mock()
  with patch.object(drafts.db,'tx',side_effect=lambda:nullcontext(t)),patch.object(drafts,'_row',return_value={'draft_choices':w}),patch.object(activity_selection,'context',return_value=(scoped,w['draft'])),patch.object(drafts.PL,'insert_roadmap') as insert:
   with self.assertRaises(ApiError):drafts.confirm(1,'p')
  insert.assert_not_called()

 def test_late_plan_regeneration_cannot_restore_results_after_goal_edit(self):
  w,_=self.state();jobs=[]
  def mutate(employee,project,fn):fn(Mock(),w);return w
  def start(kind,employee,key,work):jobs.append(work);return 'job'
  with patch.object(drafts,'_mutate',side_effect=mutate),patch.object(drafts.jobs,'start',side_effect=start),patch.object(drafts,'present',side_effect=lambda state,*_:state),patch.object(drafts.rt,'context',return_value=Mock()),patch.object(drafts.RM,'option',return_value={'id':'A1','acts':[]}),patch.object(drafts,'_maybe_support'):
   drafts.regenerate(1,'p','A1',None)
   self.assertNotIn('A1',w['v2Survey']['courseRecommendations']);self.assertIsNone(w['draftPlan'])
   drafts._apply_client(w,{'goal':'완전히 바뀐 목표'})
   jobs[0](Mock())
  self.assertIsNone(w['draft']['gen']);self.assertNotIn('v2Survey',w)

 def test_late_resource_generation_is_rejected_when_skill_scope_changes(self):
  pid=str(uuid4());w,scoped=self.state();before=copy.deepcopy(scoped);before['recommendations']=None
  after=copy.deepcopy(before);after['skillOrder']=['T'];after['skillSelectionKey']='changed'
  client=TestClient(api_app);api_app.dependency_overrides[require_employee]=lambda:Account('employee',7,'시험')
  try:
   with patch.object(api.db,'tx',side_effect=lambda:nullcontext(Mock())),patch.object(api,'course_context',side_effect=[before,after]),patch.object(api,'course_input',return_value={'id':'A1'}),patch.object(api.runtime,'context',return_value=Mock()),patch.object(api,'recommend_from_catalog',return_value={'skills':[]}),patch.object(api,'save_recommendations') as save:
    response=client.post(f'/api/v2/drafts/{pid}/recommendations?course=A1')
   self.assertEqual(response.status_code,409);save.assert_not_called()
  finally:api_app.dependency_overrides.clear()

 def test_edit_then_revert_before_save_still_resets_all_downstream_results(self):
  w,_=self.state()
  drafts._apply_client(w,{'goal':w['draft']['goal'],'resetAfter':'inputs'})
  self.assertIsNone(w['draft']['gen']);self.assertNotIn('v2Survey',w)

 def test_preview_after_material_save_uses_only_new_materials(self):
  from app.services.material_plan import preview
  w,scoped=self.state()
  scoped['resourceChoices']['S']['books']=[]
  scoped['durationEstimates']['S']={'weeks':2}
  with patch.object(drafts.RM,'_res',return_value={'hours':8,'cost':0,'estimated':[]}):plan=preview(scoped,w['draft'])
  self.assertEqual(plan['weeks'],2)
  self.assertEqual([a['res'] for a in plan['acts']],['c'])
  self.assertTrue(all(not a['task'] for a in plan['acts']))
