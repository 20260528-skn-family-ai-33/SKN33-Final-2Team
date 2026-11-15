import copy
import unittest
from unittest.mock import patch
from app.services import learning_outcomes,activity_selection
from app.errors import ApiError

class LearningOutcomesTests(unittest.TestCase):
 def setup_data(self):
  saved={'generationId':'g','project':{'goal':'검색 구현'},'recommendations':{'id':'r'},'skillOrder':['S'],'resourceChoices':{'S':{'course':'c','books':['b']}}}
  draft={'chosen':'A1','handoff':{'key':'h'},'gen':{'options':{'A1':{'id':'A1'}}}}
  resources={'c':{'id':'c','type':'course','cost':0,'content':'문서 검색','curriculum':{'items':[{'title':'검색 실습'}]},'skills':['S']},'b':{'id':'b','type':'book','cost':10000,'content':'검색 품질 평가','skills':['S']},'other':{'id':'other','content':'사용하지 않을 자료'}}
  return saved,draft,resources
 def test_selected_db_content_and_curriculum_are_passed_together(self):
  saved,draft,resources=self.setup_data()
  def generate(system,payload):
   self.assertEqual([r['id'] for r in payload['materials']],['c','b'])
   self.assertEqual(payload['materials'][0]['curriculum'][0]['title'],'검색 실습')
   self.assertEqual(payload['materials'][1]['content'],'검색 품질 평가')
   self.assertIn('명사형',system)
   return {'skillSummaries':{'S':['문서 검색 구성','검색 품질 평가','검색 결과 검증']}}
  with patch.object(activity_selection.catalog,'items',return_value=resources):result=learning_outcomes.generate(saved,draft,generate)
  saved['learningOutcomes']=result
  self.assertEqual(learning_outcomes.current(saved,draft),result['summaries'])
  saved['resourceChoices']['S']['books']=[]
  self.assertIsNone(learning_outcomes.current(saved,draft))
 def test_invalid_summary_rejected_without_mutating_inputs(self):
  saved,draft,resources=self.setup_data();before=copy.deepcopy(saved)
  with patch.object(activity_selection.catalog,'items',return_value=resources),self.assertRaises(ApiError):
   learning_outcomes.generate(saved,draft,lambda *_:{'skillSummaries':{'S':[]}})
  self.assertEqual(saved,before)

 def test_unified_instructions_keep_input_cache_key_and_summary_schema_for_all_courses(self):
  import json
  from unittest.mock import Mock
  expected={'S':['문서 검색 구성','검색 품질 평가','검색 결과 검증']}
  schema=json.loads(learning_outcomes.SYSTEM.split('JSON: ',1)[1])
  self.assertEqual(set(schema),{'skillSummaries'})
  self.assertEqual(len(schema['skillSummaries']['스킬명']),3)
  for course in ('A1','A2','A3'):
   saved,draft,resources=self.setup_data();draft['chosen']=course
   draft['gen']['options']={course:{'id':course}}
   before=copy.deepcopy((saved,draft));key=activity_selection.fingerprint(saved,draft)
   model=Mock(return_value={'skillSummaries':expected})
   with patch.object(activity_selection.catalog,'items',return_value=resources):
    _,payload=activity_selection.learning_context(saved,draft)
    out=learning_outcomes.generate(saved,draft,model)
   system,sent=model.call_args.args
   self.assertEqual(system,learning_outcomes.instructions(course))
   self.assertEqual(sent,payload)
   self.assertEqual('[Challenge 근거]' in system,course=='A3')
   self.assertEqual(out,{'key':key,'summaries':expected})
   self.assertEqual((saved,draft),before)
