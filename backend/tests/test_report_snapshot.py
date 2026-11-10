import unittest
from copy import deepcopy
from datetime import datetime,timezone
from app.services.report_snapshot import capture,matches,evidence

class ReportSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.plan={'version':1,'acts':[{'id':'course','res':'c','title':'강좌','skill':'SQL'},{'id':'task','title':'과제','skill':'SQL','how':'쿼리 및 결과 제출'}]}
        self.progress={'course':{'status':'done','memo':'학습 완료'},'task':{'status':'doing','file':{'name':'query.sql','fileId':'f'}}}
    def test_early_report_freezes_only_existing_records(self):
        snapshot=capture(self.plan,self.progress,datetime(2026,11,1,tzinfo=timezone.utc))
        self.assertTrue(snapshot['early'])
        self.assertEqual(snapshot['asOf'],'2026-11-01T00:00:00+00:00')
        self.progress['task']['status']='done';self.progress['task']['file']['name']='changed.sql'
        self.assertEqual(snapshot['activities'][1]['status'],'doing')
        self.assertEqual(snapshot['activities'][1]['file']['name'],'query.sql')
        self.assertFalse(matches(snapshot,self.plan,self.progress))
    def test_changed_memo_file_or_version_requires_new_report(self):
        snapshot=capture(self.plan,self.progress)
        self.assertTrue(matches(snapshot,self.plan,self.progress))
        for change in ('memo','file'):
            progress=deepcopy(self.progress);progress['task'][change]='changed'
            self.assertFalse(matches(snapshot,self.plan,progress))
        self.assertFalse(matches(snapshot,dict(self.plan,version=2),self.progress))
    def test_evidence_distinguishes_submission_from_verification(self):
        rows=evidence(capture(self.plan,self.progress))['activities']
        self.assertTrue(rows[1]['attachmentSubmitted'])
        self.assertFalse(rows[1]['attachmentContentVerified'])
        self.assertNotIn('fileId',str(rows))
    def test_all_done_is_not_early_and_missing_activity_is_incomplete(self):
        self.assertTrue(capture(self.plan,{})['early'])
        self.assertFalse(capture(self.plan,{key:{'status':'done'} for key in ('course','task')})['early'])

    def test_tracked_acts_leaves_out_only_books(self):
        from unittest.mock import patch
        from app.services import plans
        plan={'acts':[{'id':'course','res':'c'},{'id':'book','res':'b'},{'id':'kind','res':'k'},{'id':'task','res':None},{'id':'unknown','res':'x'}]}
        items={'c':{'type':'course','kind':'강좌'},'b':{'type':'book','kind':'도서'},'k':{'kind':'도서'}}
        with patch.object(plans.catalog,'items',return_value=items):
            self.assertEqual([act['id'] for act in plans.tracked_acts(plan)],['course','task','unknown'])
    def test_tasks_only_plan_does_not_read_catalog(self):
        from unittest.mock import patch
        from app.services import plans
        with patch.object(plans.catalog,'items') as items:
            self.assertEqual(plans.tracked_acts({'acts':[{'id':'task','res':None}]}),[{'id':'task','res':None}])
            items.assert_not_called()
    def test_snapshot_made_with_book_still_matches_book_free_plan(self):
        with_book=dict(self.plan,acts=[*self.plan['acts'],{'id':'book','res':'b','title':'도서','skill':'SQL'}])
        done={key:{'status':'done'} for key in ('course','task')}
        old=capture(with_book,done)
        self.assertTrue(old['early'])
        self.assertTrue(matches(old,self.plan,done))
        self.assertFalse(capture(self.plan,done)['early'])
    def test_report_leaves_books_out_of_done_rest_and_snapshot(self):
        from contextlib import ExitStack
        from types import SimpleNamespace
        from unittest.mock import Mock,patch
        from app.services import plans
        assess={'domain':'SQL','questions':[{'id':'q1','area':'SQL','skill':'SQL','text':'조인을 작성할 수 있다.'}],'answers':{'q1':'1'}}
        plan=dict(self.plan,goal='분석',name='계획',opt='A1',assess=assess,acts=[*self.plan['acts'],{'id':'book','res':'b','title':'도서','skill':'SQL'}])
        post={'answers':{'q1':'4'},'goalSelf':'1'}
        row={'roadmap_id':'p','project_id':1,'diagnostic_round_id':1,'content':plan}
        progress={'course':{'status':'done'},'task':{'status':'done'}}
        transaction=Mock();transaction.one.return_value=None;transaction.val.return_value='report'
        report=Mock(return_value={'good':[],'improve':[],'next':None})
        with ExitStack() as stack:
            for target,name,value in [(plans,'_owned',row),(plans,'record',{'plan':plan,'post':post,'progress':progress}),(plans,'_report_deep',None),(plans.db,'one',{}),(plans.db,'val',{}),
                                      (plans.rt,'context',Mock()),(plans.rt,'sim_once',None),(plans.DG,'level_of',{}),(plans.catalog,'items',{'c':{'type':'course'},'b':{'type':'book'}})]:
                stack.enter_context(patch.object(target,name,return_value=value))
            stack.enter_context(patch.object(plans.DG,'report',report))
            stack.enter_context(patch.object(plans.db,'J',side_effect=lambda value:value))
            stack.enter_context(patch.object(plans.db,'tx')).return_value.__enter__.return_value=transaction
            stack.enter_context(patch.object(plans.jobs,'start',side_effect=lambda kind,employee,ref,work:work(SimpleNamespace(job_id='j')) or 'j'))
            plans.report_start(1,'p')
        saved=next(call.kwargs['c'] for call in transaction.val.call_args_list if 'c' in call.kwargs)
        self.assertEqual((saved['doneTitles'],saved['restTitles']),(['강좌','과제'],[]))
        self.assertFalse(saved['executionSnapshot']['early'])
        self.assertEqual([act['id'] for act in saved['executionSnapshot']['activities']],['course','task'])
        self.assertEqual(report.call_args.args[1]['total'],2)

    def test_terminated_roadmap_cannot_resume(self):
        from unittest.mock import patch
        from app.services.plans import resume
        from app.errors import ApiError
        with patch('app.services.plans._owned',return_value={'status':'COMPLETED'}),patch('app.services.plans.db.tx') as transaction:
            with self.assertRaises(ApiError):resume(1,'plan')
            transaction.assert_not_called()
