import unittest
from copy import deepcopy
from unittest.mock import patch
from app import track_policy
from app.agents.resource_recommendations import recommend_resources
from app.services import activity_selection as activities,course_skills
from app.services.course_recommendations import scope_view

class ChallengeDepthTests(unittest.TestCase):
 def target(self):
  return {'name':'SQL','application':'대안 비교와 실행 계획 검증','targetOutcome':'쿼리 비교 및 개선 검증 보고서','completionCriteria':['동일 결과의 정합성 비교','실행 계획과 개선 근거 기록']}
 def test_only_challenge_receives_depth_guidance(self):
  for stage in ('plan','resources','tasks','summary'):
   self.assertIn('Challenge 심화 기준',track_policy.challenge_guidance('A3',stage))
   self.assertEqual(track_policy.challenge_guidance('A1',stage),'')
   self.assertEqual(track_policy.challenge_guidance('A2',stage),'')
 def test_targets_survive_selection_scope(self):
  rows=course_skills.validate_recommendations([self.target()],{'SQL'},'A3')
  scoped=scope_view({'generationId':'g'},'A3',{'learningSkills':rows})
  self.assertEqual(scoped['selection']['skills'][0],self.target())
 def test_resources_receive_targets_and_db_evidence_rule(self):
  course={'id':'A3','learningSkills':[self.target()]}
  items={'c':{'id':'c','type':'course','usable':True,'skills':['SQL'],'title':'SQL 비교 실습','cost':0,'difficulty':'ADVANCED','curriculum':{'items':[{'title':'SQL 쿼리 대안과 실행 계획 비교'}]},'content':'SQL 쿼리 대안과 실행 계획 비교'}}
  def generate(system,payload):
   self.assertIn('설명·목차',system);self.assertIn('targetOutcome',system)
   self.assertEqual(payload['course']['learningSkills'][0]['completionCriteria'],self.target()['completionCriteria'])
   return {'skills':[{'name':'SQL','courses':[{'key':'S1-C1'}],'books':[]}]}
  result=recommend_resources({'goal':'검색'},{'skills':[self.target()]},items,generate,course=course)
  self.assertEqual(result['skills'][0]['courses'][0]['id'],'c')
 def test_initial_and_reproposed_tasks_keep_challenge_targets(self):
  saved={'generationId':'g','project':{'goal':'검색'},'recommendations':{'id':'r'},'selection':{'skills':[self.target()]},'skillOrder':['SQL'],'resourceChoices':{'SQL':{'course':'c','books':[]}}}
  draft={'chosen':'A3','handoff':{'key':'h'},'gen':{'options':{'A3':{'id':'A3','learningSkills':[self.target()]}}}}
  def generate(system,payload):
   self.assertIn('단순 수강·요약·코드 실행만으로 완료 판정 금지',system)
   self.assertIn('선택 자료·강좌 근거·도달 수준 유지',system)
   self.assertEqual(payload['skillTargets']['SQL']['completionCriteria'],self.target()['completionCriteria'])
   return {'skillSummaries':{'SQL':['대안 설계','결과 비교','개선 검증']},'acts':[{'skill':'SQL','stage':2,'title':'자료 학습','res':'c','hours':2,'how':'자료 확인'},{'skill':'SQL','stage':3,'title':'쿼리 비교·개선 검증','res':None,'hours':3,'how':'두 대안을 비교한다. 결과 정합성과 실행 계획을 기록한다.'}]}
  with patch.object(activities.catalog,'items',return_value={'c':{'id':'c','type':'course','title':'비교','cost':0,'content':'비교 검증'}}),patch.object(activities.RM,'finish_option',side_effect=lambda pid,raw,source:{**raw,'acts':[dict(row,id=str(i)) for i,row in enumerate(raw['acts'])]}):
   first=activities.propose(saved,draft,generate,'test');saved['activityProposal']=deepcopy(first)
   second=activities.repropose_skill(saved,draft,'SQL',generate,'test')
  self.assertNotEqual(first['id'],second['id'])
  self.assertIn('검증',next(a for a in second['option']['acts'] if not a.get('res'))['title'])
