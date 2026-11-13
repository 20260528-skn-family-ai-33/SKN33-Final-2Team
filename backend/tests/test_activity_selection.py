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
   return propose(self.saved,self.draft,lambda *_:{'acts':self.acts if acts is None else acts,'skillSummaries':{'S':['자료 이해','프로젝트 적용','결과 검증']}},'openai')
 def test_all_proposed_activities_selected_by_default(self):
  p=self.propose();self.assertEqual(p['selectedIds'],['0','1'])
 def test_duplicate_course_activities_in_same_skill_are_merged_into_one(self):
  acts=[{'skill':'S','stage':1,'title':'학습 1','res':'c','hours':2,'how':'기초 확인'},{'skill':'S','stage':2,'title':'학습 2','res':'c','hours':2,'how':'심화 확인'},{'skill':'S','stage':3,'title':'적용','res':None,'hours':2,'how':'구현 후 확인한다.'}]
  p=self.propose(acts)
  self.assertEqual(len([a for a in p['option']['acts'] if a.get('res')=='c']),1)
  self.assertEqual(p['selectedIds'],['0','1'])
 def test_unselected_material_rejected(self):
  acts=deepcopy(self.acts);acts[0]['res']='outside'
  with self.assertRaises(ApiError):self.propose(acts)
 def test_task_only_output_includes_the_selected_course(self):
  result = self.propose(self.acts[1:])
  self.assertEqual([(act['res'], act['title']) for act in result['option']['acts']],
                   [('c', '자료'), (None, '적용')])
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

 def test_reproposal_keeps_previous_versions_and_per_version_selection(self):
  from app.services.activity_selection import append_proposal,versions,view
  first=self.propose();first['selectedIds']=['1']
  append_proposal(self.saved,self.draft,first)
  second=self.propose();append_proposal(self.saved,self.draft,second)
  history=versions(self.saved,self.draft)
  self.assertEqual([p['id'] for p in history],[first['id'],second['id']])
  self.assertEqual(history[0]['selectedIds'],['1'])
  self.assertEqual(view(self.saved,self.draft)['proposal']['id'],second['id'])
  self.assertEqual(selection_option(self.saved,self.draft,['1'],first['id'])['acts'][0]['title'],'적용')
  with self.assertRaises(ApiError):selection_option(self.saved,self.draft,['1'],'unknown')

 def test_changed_materials_hide_old_comparison_versions(self):
  from app.services.activity_selection import append_proposal,versions
  append_proposal(self.saved,self.draft,self.propose())
  self.saved['resourceChoices']['S']['books']=['changed']
  self.assertEqual(versions(self.saved,self.draft),[])

 def test_legacy_proposal_gets_stable_comparison_identifier(self):
  from app.services.activity_selection import versions
  old=self.propose();old.pop('id');self.saved['activityProposal']=old
  first=versions(self.saved,self.draft);second=versions(self.saved,self.draft)
  self.assertEqual(first[0]['id'],second[0]['id'])
  self.assertNotIn('id',old)

 def test_reproposal_sends_previous_tasks_and_keeps_selected_inputs(self):
  previous=[self.propose()]
  def generate(system,payload):
   self.assertEqual(payload['skillOrder'],['S'])
   self.assertEqual(payload['choices'],self.saved['resourceChoices'])
   self.assertEqual([row['id'] for row in payload['materials']],['c'])
   self.assertEqual(payload['previousProposals'][0]['acts'],previous[0]['option']['acts'])
   self.assertIn('구별되는',system)
   return {'acts':self.acts,'skillSummaries':{'S':['자료 이해','프로젝트 적용','결과 검증']}}
  with patch('app.services.activity_selection.catalog.items',return_value={'c':{'id':'c','title':'자료','cost':0}}),patch('app.services.activity_selection.RM.finish_option',side_effect=lambda pid,raw,source:{**raw,'acts':[dict(a,id=str(i)) for i,a in enumerate(raw['acts'])]}):
   result=propose(self.saved,self.draft,generate,'test',previous=previous)
  self.assertNotEqual(result['id'],previous[0]['id'])

 def test_combined_competency_summary_is_preserved(self):
  self.assertEqual(self.propose()['skillSummaries'],{'S':['자료 이해','프로젝트 적용','결과 검증']})

 def test_each_skill_requires_an_output_task(self):
  with self.assertRaises(ApiError):self.propose(self.acts[:1])

 def test_invalid_competency_summary_is_rejected(self):
  for summaries in (None,{}, {'S':['하나']}, {'S':['하나','둘','']}, {'other':['하나','둘','셋']}):
   with self.subTest(summaries=summaries), patch('app.services.activity_selection.catalog.items',return_value={'c':{'id':'c','title':'자료','cost':0}}):
    with self.assertRaises(ApiError):
     propose(self.saved,self.draft,lambda *_:{'acts':self.acts,'skillSummaries':summaries},'test')

 def test_single_skill_reproposal_preserves_materials_other_skills_and_selection(self):
  from app.services import activity_selection as activities
  saved=deepcopy(self.saved);saved['skillOrder']=['S','T'];saved['resourceChoices']['T']={'course':None,'books':[]}
  base=self.propose();base['key']=activities.fingerprint(saved,self.draft)
  base['option']['acts'] += [{'id':'keep-task','skill':'T','res':None,'title':'보존 과제','hours':3,'how':'기존 설명'}]
  base['skillSummaries']['T']=['기초','적용','검증'];base['selectedIds']=['0','keep-task']
  saved['activityProposal']=base;before=deepcopy(base)
  replacement={'id':'new','option':{'acts':[{'id':'new-task','skill':'S','res':None,'title':'새 과제','hours':9,'how':'새 설명'}]},'skillSummaries':{'S':['하나','둘','셋']}}
  with patch.object(activities,'propose',return_value=replacement) as generate:
   result=activities.repropose_skill(saved,self.draft,'S',lambda *_:None,'test')
  self.assertEqual(generate.call_args.args[0]['skillOrder'],['S'])
  self.assertEqual(result['option']['acts'][0],before['option']['acts'][0])
  self.assertEqual(next(a for a in result['option']['acts'] if a['id']=='keep-task'),before['option']['acts'][-1])
  self.assertIn('keep-task',result['selectedIds']);self.assertEqual(base,before)
  self.assertEqual(result['skillSummaries'],before['skillSummaries'])

 def test_material_period_does_not_increase_with_task_hours(self):
  from app.services import activity_selection as activities
  from app.agents import roadmap
  saved=deepcopy(self.saved);saved['skillOrder']=['S','T'];saved['resourceChoices']['T']={'course':None,'books':[]}
  saved['durationEstimates']={'S':{'weeks':5},'T':{'weeks':8}}
  base=self.propose();base['key']=activities.fingerprint(saved,self.draft)
  base['option'].update(id='A2',name='Crash',short='기초',tagline='목표')
  base['option']['acts']=[{'id':'s','skill':'S','stage':3,'title':'과제 S','res':None,'hours':100,'how':'설명'},{'id':'t','skill':'T','stage':3,'title':'과제 T','res':None,'hours':100,'how':'설명'}]
  saved['activityProposal']=base
  option=activities.selection_option(saved,self.draft,['s','t'])
  plan=roadmap.build_plan(option,{'hours':4},'목표')
  self.assertEqual(plan['weeks'],13)
  self.assertEqual(plan['acts'][0]['skill'],'S')
  self.assertEqual(plan['acts'][1]['wTo'],13)

 def test_inline_skill_choices_compose_and_preserve_other_skills(self):
  from app.services.activity_selection import append_proposal,compose_skill_selection
  first=self.propose()
  first['option']['acts'].append({'id':'t-old','skill':'T','res':None,'title':'T old','hours':2,'how':'verify'})
  append_proposal(self.saved,self.draft,first)
  second=deepcopy(first);second['id']='second'
  second['option']['acts'][1]['id']='s-new'
  second['option']['acts'][-1]['id']='t-new'
  append_proposal(self.saved,self.draft,second)
  result=compose_skill_selection(self.saved,self.draft,first['id'],{'S':'second'})
  self.assertEqual([a['id'] for a in result['option']['acts']],['0','s-new','t-old'])
  self.assertEqual(first['option']['acts'][1]['id'],'1')
  append_proposal(self.saved,self.draft,result)
  selected=selection_option(self.saved,self.draft,['0','s-new','t-old'],result['id'])
  self.assertEqual([a['id'] for a in selected['acts']],['0','s-new','t-old'])
  self.assertEqual(current_record(self.saved,self.draft)['skillProposalIds'],{'S':'second'})
  with self.assertRaises(ApiError):compose_skill_selection(self.saved,self.draft,first['id'],{'S':'missing'})
  with self.assertRaises(ApiError):compose_skill_selection(self.saved,self.draft,first['id'],{'outside':'second'})

 def test_task_prompt_requires_course_based_evaluable_submission(self):
  from app.services.activity_selection import SYSTEM
  for requirement in ['choices[스킬].course','만들 것:','필수 항목:','제출물:','평가 기준:','사후 점검과 역량 보고서','선택 도서는','재제안은 같은 스킬']:
   self.assertIn(requirement,SYSTEM)

 def test_integrated_instructions_keep_payload_and_output_contract_all_courses(self):
  import json
  from app.services import activity_selection as activities
  from app.services.activity_instructions import instructions,SCHEMA
  for pid in ('A1','A2','A3'):
   saved=deepcopy(self.saved);draft=deepcopy(self.draft)
   draft['chosen']=pid;draft['gen']['options'][pid]={'id':pid}
   before=deepcopy((saved,draft))
   with patch.object(activities.catalog,'items',return_value={'c':{'id':'c','title':'자료','cost':0}}),patch.object(activities.RM,'finish_option',side_effect=lambda pid,raw,source:{**raw,'acts':[dict(a,id=str(i)) for i,a in enumerate(raw['acts'])]}):
    _,expected=activities.learning_context(saved,draft)
    key=activities.fingerprint(saved,draft)
    def generate(system,payload):
     self.assertEqual(system,instructions(pid));self.assertEqual(payload,expected)
     self.assertEqual(json.loads(system.split('JSON: ',1)[1].split('\n',1)[0]),SCHEMA)
     self.assertEqual('[Challenge 과제]' in system,pid=='A3')
     self.assertEqual('[Crash 핵심 완료 기준]' in system,pid=='A2')
     return {'acts':deepcopy(self.acts),'skillSummaries':{'S':['자료 이해','프로젝트 적용','결과 검증']}}
    result=activities.propose(saved,draft,generate,'mock')
    self.assertEqual(result['key'],key)
    self.assertEqual(result['selectedIds'],['0','1'])
   self.assertEqual((saved,draft),before)

 def test_roadmap_style_acts_schema_normalized(self):
  # 파인튜닝 모델이 산출물 과제에 skills(리스트)를 넣고, 자료 활동에 skill 키를 생략한 경우
  acts = [
   {'stage': 2, 'title': '학습', 'res': 'c', 'hours': 2, 'how': '학습 설명'},
   {'stage': 3, 'title': '적용', 'res': None, 'hours': 2, 'how': '구현 설명', 'skills': ['S']}
  ]
  p = self.propose(acts)
  self.assertEqual(len(p['option']['acts']), 2)
  self.assertEqual(p['option']['acts'][0]['skill'], 'S')
  self.assertEqual(p['option']['acts'][1]['skill'], 'S')

 def test_wrapped_answer_envelope_supported(self):
  with patch('app.services.activity_selection.catalog.items', return_value={'c': {'id': 'c', 'title': '자료', 'cost': 0}}), \
       patch('app.services.activity_selection.RM.finish_option', side_effect=lambda pid, raw, source: {**raw, 'acts': [dict(a, id=str(i)) for i, a in enumerate(raw['acts'])]}):
   p = propose(self.saved, self.draft, lambda *_: {'answer': {'acts': self.acts, 'skillSummaries': {'S': ['이해', '적용', '검증']}}, 'type': 'agent'}, 'test')
  self.assertEqual(p['selectedIds'], ['0', '1'])
