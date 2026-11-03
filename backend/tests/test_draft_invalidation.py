import copy
import json
import unittest
from unittest.mock import Mock
from app.services import drafts,survey_store
import test_survey_generation as fixtures

class InvalidationTests(unittest.TestCase):
 def state(self):
  d=drafts.fresh_draft();d.update(goal='원래 목표',detailsOk=True,gen={'key':'old','options':{}},handoff={'key':'old'},chosen='A1',doc={'status':'ok','summary':'이전 요약'})
  return {'gp5':1,'draft':d,'draftPlan':{'opt':'A1'},'v2Survey':{'completed':True}}
 def test_each_upstream_change_clears_survey_and_all_downstream_results(self):
  for body in ({'goal':'수정 목표'},{'prefs':{'hours':8}},{'project':{'name':'변경.pdf'}},{'docSummary':'새 요약'}):
   with self.subTest(body=body):
    w=self.state();drafts._apply_client(w,body)
    self.assertNotIn('v2Survey',w);self.assertIsNone(w['draft']['gen']);self.assertIsNone(w['draft']['handoff']);self.assertIsNone(w['draftPlan'])
    self.assertIsNone(w['draft']['quiz']);self.assertFalse(w['draft']['detailsOk'])
 def test_navigation_and_identical_input_do_not_reset_results(self):
  w=self.state();before=copy.deepcopy(w)
  drafts._apply_client(w,{'goal':'원래 목표','lastNew':'new-quiz'})
  self.assertEqual(w['draft']['gen'],before['draft']['gen']);self.assertIn('v2Survey',w)
 def test_changed_answers_clear_cached_plans_in_same_write_and_unchanged_answers_keep_completion(self):
  fixture=fixtures.SurveyTests();fixture.setUp();t=Mock();t.run.return_value=1
  t.one.return_value={'draft_choices':{'draft':drafts.fresh_draft()}}
  value=survey_store.save_generated(t,1,'p',fixture.project,fixture.selection(1),fixture.profile,fixture.result(1))
  answers={q['id']:(1 if kind=='surveys' else 0) for g in value['survey']['groups'] for kind in ('surveys','quizzes') for q in g[kind]}
  value.update(answers=answers,completed=True,courseRecommendations={'A1':{'activityProposal':{'old':True}}})
  raw={'draft':dict(drafts.fresh_draft(),gen={'key':'old','options':{}},handoff={'key':'old'}),'v2Survey':value}
  t.one.return_value={'draft_choices':raw}
  result=survey_store.save_answers(t,1,'p',value['generationId'],answers,complete=False)
  self.assertTrue(result['completed']);self.assertIn('courseRecommendations',result)
  changed=dict(answers);changed[next(iter(changed))]=2
  result=survey_store.save_answers(t,1,'p',value['generationId'],changed,complete=True)
  self.assertNotIn('courseRecommendations',result)
  self.assertIsNone(json.loads(t.run.call_args.kwargs['draft'])['gen'])
  self.assertIn("'{draftPlan}'",t.run.call_args.args[0])
