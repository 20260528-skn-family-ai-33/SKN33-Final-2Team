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

    def test_terminated_roadmap_cannot_resume(self):
        from unittest.mock import patch
        from app.services.plans import resume
        from app.errors import ApiError
        with patch('app.services.plans._owned',return_value={'status':'COMPLETED'}),patch('app.services.plans.db.tx') as transaction:
            with self.assertRaises(ApiError):resume(1,'plan')
            transaction.assert_not_called()
