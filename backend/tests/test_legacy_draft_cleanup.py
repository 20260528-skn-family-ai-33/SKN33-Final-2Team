"""구형 미확정 초안 정리의 보존 범위·경쟁 변경·백업 실패 계약. 실제 DB는 별도 검사한다."""
from contextlib import nullcontext
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from tools import cleanup_legacy_drafts as cleanup

KEY='11111111-1111-4111-8111-111111111111'


def old():
    return {'project_id':KEY,'employee_id':1,'status':'DRAFTING',
            'draft_choices':{'gp5':1,'draft':{'quiz':{'questions':[{'id':'q'}]},'answers':{'q':'4'}}}}


class CleanupTests(unittest.TestCase):
    def test_only_legacy_unconfirmed_quiz_drafts_are_identified(self):
        self.assertTrue(cleanup.legacy(old()))
        for state in (None,{},[],{'gp5':1,'draft':{}},{'gp5':1,'draft':{'quiz':'bad'}}):
            row=old();row['draft_choices']=state
            self.assertFalse(cleanup.legacy(row))
        for status in ('IN_PROGRESS','COMPLETED','ARCHIVED'):
            row=old();row['status']=status
            self.assertFalse(cleanup.legacy(row))

    def test_new_survey_key_even_empty_and_new_handoff_are_preserved(self):
        for value in (None,{}, {'completed':False},{'completed':True}):
            row=old();row['draft_choices']['v2Survey']=value
            self.assertFalse(cleanup.legacy(row))
        row=old();row['draft_choices']['draft']['handoff']={'assessmentGenerationId':'new'}
        self.assertFalse(cleanup.legacy(row))

    def test_dry_run_excludes_records_with_confirmation_reports_or_post_assessment(self):
        first=old();second=deepcopy(first);second['project_id']='22222222-2222-4222-8222-222222222222'
        t=Mock();t.one.return_value={'name':'test','oid':'1'}
        with patch.object(cleanup,'rows',return_value=[first,second]),patch.object(cleanup,'protected',side_effect=[False,True]):
            report=cleanup.inspect(t)
        self.assertEqual([r['project_id'] for r in report['candidates']],[KEY])
        self.assertEqual(report['skipped'],1)
        t.run.assert_not_called()

    def test_input_change_after_review_stops_before_backup_and_delete(self):
        row=old();expected=cleanup.digest(row);row['draft_choices']['draft']['answers']['q']='5'
        t=Mock()
        with TemporaryDirectory() as temp,patch.object(cleanup.db,'tx',return_value=nullcontext(t)), \
                patch.object(cleanup,'schema_guard'),patch.object(cleanup,'rows',return_value=[row]), \
                patch.object(cleanup,'protected',return_value=False):
            backup=Path(temp)/'backup.json'
            with self.assertRaisesRegex(ValueError,'바뀌었'):
                cleanup.apply([KEY],backup,{KEY:expected})
            self.assertFalse(backup.exists())
            t.all.assert_not_called()

    def test_protected_target_stops_before_any_delete(self):
        row=old();t=Mock()
        with TemporaryDirectory() as temp,patch.object(cleanup.db,'tx',return_value=nullcontext(t)), \
                patch.object(cleanup,'schema_guard'),patch.object(cleanup,'rows',return_value=[row]), \
                patch.object(cleanup,'protected',return_value=True):
            with self.assertRaises(ValueError):cleanup.apply([KEY],Path(temp)/'b.json',{KEY:cleanup.digest(row)})
            t.all.assert_not_called()

    def test_backup_must_be_saved_before_exact_id_delete(self):
        row=old();t=Mock();t.one.return_value={'name':'test','oid':'1'}
        def query(sql,**params):
            if sql.startswith('DELETE'):
                payload=json.loads(backup.read_text(encoding='utf-8'))
                self.assertEqual(payload['tables']['projects'],[row])
                self.assertEqual(payload['sha256'],cleanup.digest(payload['tables']))
                self.assertEqual(params['ids'],[KEY])
                return [{'id':KEY}]
            return []
        t.all.side_effect=query
        with TemporaryDirectory() as temp,patch.object(cleanup.db,'tx',return_value=nullcontext(t)), \
                patch.object(cleanup,'schema_guard'),patch.object(cleanup,'rows',return_value=[row]), \
                patch.object(cleanup,'protected',return_value=False):
            backup=Path(temp)/'b.json'
            self.assertEqual(cleanup.apply([KEY],backup,{KEY:cleanup.digest(row)})['deleted'],1)

    def test_existing_backup_is_not_overwritten_or_used_to_delete(self):
        row=old();t=Mock();t.one.return_value={};t.all.return_value=[]
        with TemporaryDirectory() as temp,patch.object(cleanup.db,'tx',return_value=nullcontext(t)), \
                patch.object(cleanup,'schema_guard'),patch.object(cleanup,'rows',return_value=[row]), \
                patch.object(cleanup,'protected',return_value=False):
            backup=Path(temp)/'b.json';backup.write_text('keep',encoding='utf-8')
            with self.assertRaises(FileExistsError):cleanup.apply([KEY],backup,{KEY:cleanup.digest(row)})
            self.assertEqual(backup.read_text(),'keep')
            self.assertFalse(any(c.args[0].startswith('DELETE') for c in t.all.call_args_list))

    def test_unknown_dependent_schema_is_not_silently_deleted(self):
        t=Mock();t.all.return_value=[{'schema':'public','child':'new_history'}]
        with self.assertRaisesRegex(ValueError,'관련 테이블'):cleanup.schema_guard(t)

    def test_bad_ids_fail_before_connection(self):
        with patch.object(cleanup.db,'tx') as tx:
            for ids in ([],['not-a-uuid']):
                with self.assertRaises(ValueError):cleanup.apply(ids,Path('unused'),{})
            tx.assert_not_called()

    def test_corrupt_backup_and_different_database_cannot_restore(self):
        backup={'format':cleanup.FORMAT,'database':{'name':'original','oid':'1'},'tables':{k:[] for k in cleanup.TABLES}}
        backup['tables']['projects']=[old()];backup['sha256']='wrong'
        with TemporaryDirectory() as temp:
            path=Path(temp)/'b.json';path.write_text(json.dumps(backup),encoding='utf-8')
            with patch.object(cleanup.db,'tx') as tx:
                with self.assertRaisesRegex(ValueError,'해시'):cleanup.restore(path)
                tx.assert_not_called()
            backup['sha256']=cleanup.digest(backup['tables']);path.write_text(json.dumps(backup),encoding='utf-8')
            t=Mock();t.one.return_value={'name':'other','oid':'2'}
            with patch.object(cleanup.db,'tx',return_value=nullcontext(t)):
                with self.assertRaisesRegex(ValueError,'DB와'):cleanup.restore(path)
                t.run.assert_not_called()


if __name__=='__main__':
    unittest.main()
