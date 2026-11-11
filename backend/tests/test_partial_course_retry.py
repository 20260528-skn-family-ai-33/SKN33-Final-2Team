import copy
import unittest
from unittest.mock import Mock, patch
from app.services import drafts
from app.errors import AgentError

class PartialCourseRetryTests(unittest.TestCase):
    def state(self):
        free={'id':'A1','acts':[{'id':'keep','title':'보존'}]}
        challenge={'id':'A3','acts':[]}
        return {'draft':{'handoff':{},'chosen':'A1','gen':{'key':'h','options':{'A1':free,'A3':challenge},'missing':['A2']},
            'genRun':{'key':'h','rows':{'A1':{'st':'ok','out':free},'A2':{'st':'fail','out':None},'A3':{'st':'ok','out':challenge}}}},'draftPlan':{'opt':'A1','marker':'keep'}}

    def run_retry(self,w,fail=False):
        def mutate(employee,draft,fn):fn(Mock(),w);return w
        def start(kind,employee,key,fn,*,before_start):
            before_start('mock-job')
            fn(Mock(job_id='mock-job'))
            return 'mock-job'
        with patch.object(drafts,'_mutate',side_effect=mutate),patch.object(drafts.jobs,'start',side_effect=start),patch.object(drafts.rt,'context',return_value=Mock(provider='openai',fail_sim={})),patch.object(drafts.RM,'option',side_effect=AgentError('실패') if fail else None,return_value={'id':'A2','acts':[]}):
            return drafts._run_option(1,'draft','A2')

    def test_retry_fills_only_missing_course_and_keeps_selected_plan(self):
        w=self.state();before=copy.deepcopy(w)
        self.run_retry(w)
        self.assertEqual(w['draft']['gen']['missing'],[])
        self.assertEqual(w['draft']['gen']['options']['A1'],before['draft']['gen']['options']['A1'])
        self.assertEqual(w['draft']['gen']['options']['A3'],before['draft']['gen']['options']['A3'])
        self.assertEqual(w['draft']['chosen'],'A1')
        self.assertEqual(w['draftPlan'],before['draftPlan'])
        self.assertEqual(w['draft']['gen']['options']['A2']['id'],'A2')

    def test_failed_retry_preserves_successful_courses(self):
        w=self.state();before=copy.deepcopy(w)
        with self.assertRaises(AgentError):self.run_retry(w,fail=True)
        self.assertEqual(w['draft']['gen'],before['draft']['gen'])
        self.assertEqual(w['draftPlan'],before['draftPlan'])
