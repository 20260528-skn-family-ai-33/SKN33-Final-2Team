"""동일 설문 ID 대응·보고서 저장 스냅샷·본인 공개 범위를 검증한다."""
from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from app.services import plans


class ReportSurveyTests(unittest.TestCase):
    def test_report_saves_each_question_by_id_even_when_skill_is_the_same(self):
        assess = {'domain':'SQL', 'questions':[
            {'id':'q1','area':'SQL','skill':'SQL','text':'조인을 작성할 수 있다.'},
            {'id':'q2','area':'SQL','skill':'SQL','text':'인덱스를 설명할 수 있다.'}], 'answers':{'q1':'1','q2':'3'}}
        plan = {'version':1,'goal':'분석','name':'계획','opt':'A1','acts':[], 'assess':assess}
        post = {'answers':{'q2':'4','q1':'5'},'goalSelf':'1'}
        row = {'roadmap_id':'p','project_id':1,'diagnostic_round_id':1,'content':plan}
        transaction = Mock()
        transaction.one.side_effect = [None, {'content': plan}]
        transaction.all.return_value = []
        transaction.val.side_effect = lambda sql, **kw: 'IN_PROGRESS' if 'SELECT status::text' in sql else 'report'
        with ExitStack() as stack:
            stack.enter_context(patch.object(plans,'_owned',return_value=row))
            stack.enter_context(patch.object(plans,'record',return_value={'plan':plan,'post':post,'progress':{}}))
            stack.enter_context(patch.object(plans,'_report_deep',return_value=None))
            stack.enter_context(patch.object(plans.db,'one',return_value={}))
            stack.enter_context(patch.object(plans.db,'val',return_value={}))
            stack.enter_context(patch.object(plans.db,'J',side_effect=lambda value:value))
            tx = stack.enter_context(patch.object(plans.db,'tx'))
            tx.return_value.__enter__.return_value = transaction
            stack.enter_context(patch.object(plans.rt,'context',return_value=Mock()))
            stack.enter_context(patch.object(plans.rt,'sim_once',return_value=None))
            stack.enter_context(patch.object(plans.DG,'report',return_value={'good':[],'improve':[],'next':None}))
            stack.enter_context(patch.object(plans.DG,'level_of',return_value={}))
            stack.enter_context(patch.object(plans.jobs,'start',side_effect=lambda kind,employee,ref,work, **kwargs: work(SimpleNamespace(job_id='j')) or 'j'))
            plans.report_start(1,'p')
        saved = next(call.kwargs['c'] for call in transaction.val.call_args_list if 'c' in call.kwargs)
        evidence = saved['surveyEvidence']
        self.assertEqual([(x['id'],x['pre'],x['post']) for x in evidence],[('q1','1','5'),('q2','3','4')])
        self.assertEqual(evidence[0]['text'],'조인을 작성할 수 있다.')
        post['answers']['q1']='2'
        self.assertEqual(evidence[0]['post'],'5')

    def test_raw_comparison_is_only_sent_to_owner_and_old_reports_still_load(self):
        rows = [{'report_id':'r','roadmap_id':'p','report_content':{'gained':[], 'surveyEvidence':[{'id':'q1'}]},'created_at':datetime.now(timezone.utc),'confirmed':False}]
        with patch.object(plans.db,'all_',return_value=rows):
            self.assertIn('surveyEvidence',plans.reports(1)[0])
            self.assertNotIn('surveyEvidence',plans.reports(1,for_mgr=True)[0])
            rows[0]['report_content'].pop('surveyEvidence')
            self.assertEqual(plans.reports(1)[0]['gained'],[])
