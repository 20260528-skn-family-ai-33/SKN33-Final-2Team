"""결과 보고서 과제(#96): 입력 검증, 알림과의 트랜잭션, 제출 규칙, 첨부 저장·내려받기, API 권한을 검사한다."""
from contextlib import contextmanager
from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth
from app.errors import ApiError, api_error_handler
from app.routers import team, work
from app.services import notifications as NT, plans, report_tasks as RT

RID = '11111111-1111-1111-1111-111111111111'
TID = '22222222-2222-2222-2222-222222222222'


@contextmanager
def tx_of(t):
    yield t


REPORT = {'planId': RID, 'goal': '분석 자동화', 'opt': 'A2', 'good': ['좋음'], 'improve': ['보완'], 'next': {'goal': '다음', 'why': '이유'},
          'gained': [{'skill': 'SQL', 'from': '2', 'to': '4'}], 'still': [{'skill': 'RAG', 'from': '2', 'to': '2'}],
          'doneTitles': ['활동1'], 'restTitles': ['활동2']}


class SendTests(unittest.TestCase):
    def send(self, body, reports=(REPORT,)):
        t = Mock()
        t.val.return_value = TID
        with patch.object(RT.PL, 'reports', return_value=list(reports)) as reps, patch.object(RT.db, 'tx', side_effect=lambda: tx_of(t)), \
                patch.object(RT, 'of_plan', return_value=['목록']), patch.object(NT, 'task_sent') as notify:
            out = RT.send(3, 8, RID, body)
        return out, t, notify, reps

    def test_saves_and_notifies_the_member_in_the_same_transaction(self):
        out, t, notify, reps = self.send('  보고서를 보고 정리해 주세요  ')
        self.assertEqual(out, ['목록'])
        self.assertEqual(t.val.call_args.kwargs, {'r': RID, 'm': 8, 'h': 3, 'b': '보고서를 보고 정리해 주세요'})
        notify.assert_called_once_with(t, 3, 8, RID, TID)
        reps.assert_called_once_with(8, for_mgr=True)

    def test_rejects_empty_and_too_long(self):
        for body, code in (('   ', 'TASK_EMPTY'), (None, 'TASK_EMPTY'), ('가' * (RT.BODY_MAX + 1), 'TASK_TOO_LONG')):
            with self.assertRaises(ApiError) as e:
                self.send(body)
            self.assertEqual((e.exception.status, e.exception.code), (400, code))

    def test_needs_a_report_on_that_roadmap(self):
        with self.assertRaises(ApiError) as e:
            self.send('과제', reports=[dict(REPORT, planId='other')])
        self.assertEqual((e.exception.status, e.exception.code), (409, 'NO_REPORT'))


class SubmitTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.var = Path(folder.name)

    def submit(self, answer, name=None, raw=None, row=None):
        t = Mock()
        t.one.return_value = {'head_id': 3, 'submitted_at': None} if row is None else row or None
        with patch.object(RT.PL, '_owned', return_value={}) as owned, patch.object(RT.db, 'tx', side_effect=lambda: tx_of(t)), patch.object(RT.db, 'J', side_effect=lambda v: v), \
                patch.object(RT, 'of_plan', return_value=['목록']), patch.object(NT, 'task_submitted') as notify, patch.object(RT, 'S', SimpleNamespace(var_dir=self.var)):
            out = RT.submit(8, RID, TID, answer, name, raw)
        return out, t, notify, owned

    def test_text_only_notifies_the_head_who_sent_it(self):
        out, t, notify, owned = self.submit('  결과예요 ')
        self.assertEqual(out, ['목록'])
        owned.assert_called_once_with(8, RID)
        self.assertEqual(t.run.call_args.kwargs, {'a': '결과예요', 'f': None, 't': TID})
        notify.assert_called_once_with(t, 8, 3, RID, TID)

    def test_file_is_stored_under_a_server_generated_name(self):
        _, t, _, _ = self.submit('', '../../악성.exe', b'data')
        saved = t.run.call_args.kwargs['f']
        self.assertEqual((saved['name'], saved['size']), ('../../악성.exe', 4))
        self.assertRegex(saved['fileId'], r'^[0-9a-f]{32}$')
        self.assertEqual((self.var / 'uploads' / saved['fileId']).read_bytes(), b'data')
        self.assertEqual([p.name for p in (self.var / 'uploads').iterdir()], [saved['fileId']])

    def test_needs_text_or_file_and_respects_limits(self):
        for args, status, code in ((('   ',), 400, 'SUBMISSION_EMPTY'), (('', 'a.txt', b''), 400, 'SUBMISSION_EMPTY'), (('가' * (RT.ANSWER_MAX + 1),), 400, 'ANSWER_TOO_LONG'),
                                   (('', 'a.bin', b'x' * (RT.MAX_FILE + 1)), 413, 'FILE_TOO_BIG')):
            with self.assertRaises(ApiError) as e:
                self.submit(*args)
            self.assertEqual((e.exception.status, e.exception.code), (status, code))

    def test_only_once_and_only_own_task(self):
        with self.assertRaises(ApiError) as e:
            self.submit('결과', row={'head_id': 3, 'submitted_at': datetime(2026, 11, 9, tzinfo=timezone.utc)})
        self.assertEqual((e.exception.status, e.exception.code), (409, 'ALREADY_SUBMITTED'))
        with self.assertRaises(ApiError) as e:
            self.submit('결과', row={})  # 다른 직원의 과제·없는 과제
        self.assertEqual(e.exception.status, 404)
        with self.assertRaises(ApiError) as e:
            with patch.object(RT.PL, '_owned', return_value={}):
                RT.submit(8, RID, 'not-a-uuid', '결과')
        self.assertEqual(e.exception.status, 404)

    def test_failed_save_leaves_no_notification(self):
        t = Mock()
        t.one.return_value = {'head_id': 3, 'submitted_at': None}
        t.run.side_effect = RuntimeError('저장 실패')
        with patch.object(RT.PL, '_owned', return_value={}), patch.object(RT.db, 'tx', side_effect=lambda: tx_of(t)), patch.object(NT, 'task_submitted') as notify, \
                self.assertRaises(RuntimeError):
            RT.submit(8, RID, TID, '결과')
        notify.assert_not_called()


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.var = Path(folder.name)
        (self.var / 'uploads').mkdir()
        (self.var / 'uploads' / 'abc').write_bytes(b'data')

    def of(self, row, task=TID):
        with patch.object(RT.db, 'one', return_value=row) as q, patch.object(RT, 'S', SimpleNamespace(var_dir=self.var)):
            return RT.attachment_of(8, RID, task), q

    def test_uses_the_stored_id_and_scopes_to_the_member(self):
        (path, name), q = self.of({'attachment': {'fileId': 'abc', 'name': '결과.pdf', 'size': 4}})
        self.assertEqual((path.name, name), ('abc', '결과.pdf'))
        self.assertEqual(q.call_args.kwargs, {'t': TID, 'r': RID, 'e': 8})

    def test_missing_rows_files_and_bad_ids_are_404(self):
        for row in (None, {'attachment': None}, {'attachment': {'fileId': 'gone', 'name': 'x', 'size': 1}}):
            with self.assertRaises(ApiError) as e:
                self.of(row)
            self.assertEqual(e.exception.status, 404)
        with self.assertRaises(ApiError) as e:
            self.of({}, task='not-a-uuid')
        self.assertEqual(e.exception.status, 404)


class ViewTests(unittest.TestCase):
    def test_view_hides_the_stored_file_id(self):
        at = datetime(2026, 11, 9, tzinfo=timezone.utc)
        out = RT._view({'task_id': TID, 'roadmap_id': RID, 'head_id': 3, 'head_name': '부서장', 'body': '과제', 'created_at': at, 'submitted_at': at, 'answer': None,
                        'attachment': {'fileId': 'secret', 'name': '결과.pdf', 'size': 4}})
        self.assertEqual(out, {'id': TID, 'planId': RID, 'body': '과제', 'createdAt': '2026-11-09', 'head': {'id': '3', 'name': '부서장'}, 'submittedAt': '2026-11-09', 'answer': '',
                               'file': {'name': '결과.pdf', 'size': 4}})


class NotificationRowTests(unittest.TestCase):
    def test_directions(self):
        t = Mock()
        NT.task_sent(t, 3, 8, RID, TID)
        (sql, ), kw = t.run.call_args
        self.assertIn("'task', 'member'", sql)
        self.assertEqual(kw, {'m': 8, 'h': 3, 'r': RID, 'i': TID})
        NT.task_submitted(t, 8, 3, RID, TID)
        (sql, ), kw = t.run.call_args
        self.assertIn("'task_result', 'head'", sql)
        self.assertEqual(kw, {'h': 3, 'm': 8, 'r': RID, 'i': TID})

    def test_inbox_points_task_notifications_at_the_current_report(self):
        with patch.object(NT.db, 'all_', return_value=[]) as q, patch.object(NT.db, 'val', return_value=0):
            NT.inbox(7)
        self.assertIn("n.kind IN ('task', 'task_result')", q.call_args.args[0])
        self.assertIn('ORDER BY g.created_at DESC LIMIT 1', q.call_args.args[0])


class ApiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(team.r)
        app.include_router(work.r)
        app.add_exception_handler(ApiError, api_error_handler)
        self.client = TestClient(app)
        self.head_view = patch.object(team.profile, 'view', return_value={'supervisor': True, 'members': [{'id': 8}]})
        self.head_view.start()
        self.addCleanup(self.head_view.stop)

    def as_account(self, account):
        p = patch.object(auth, 'account_of', return_value=account)
        p.start()
        self.addCleanup(p.stop)

    def test_anonymous_and_admin_cannot_use_tasks(self):
        self.as_account(None)
        for path in (f'/api/v1/plans/{RID}/tasks', f'/api/v1/team/plans/{RID}/tasks'):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.as_account(auth.Account('admin', 1, '관리자'))
        self.assertEqual(self.client.get(f'/api/v1/team/plans/{RID}/tasks').status_code, 403)

    def test_non_head_cannot_use_team_routes(self):
        self.as_account(auth.Account('employee', 8, '직원'))
        with patch.object(team.profile, 'view', return_value={'supervisor': False, 'members': []}), patch.object(RT, 'send') as send:
            self.assertEqual(self.client.post(f'/api/v1/team/plans/{RID}/tasks', json={'body': '과제'}).status_code, 403)
        send.assert_not_called()

    def test_head_cannot_reach_a_plan_outside_the_team(self):
        self.as_account(auth.Account('employee', 3, '부서장'))
        with patch.object(team.profile, 'member_ids', return_value=[8]), patch.object(team.PL, '_base_rows', return_value=[]), patch.object(RT, 'send') as send, patch.object(RT, 'attachment_of') as file:
            self.assertEqual(self.client.post(f'/api/v1/team/plans/{RID}/tasks', json={'body': '과제'}).status_code, 404)
            self.assertEqual(self.client.get(f'/api/v1/team/plans/{RID}/tasks/{TID}/file').status_code, 404)
        send.assert_not_called()
        file.assert_not_called()

    def in_team(self):
        for p in (patch.object(team.profile, 'member_ids', return_value=[8]), patch.object(team.PL, '_base_rows', return_value=[{}])):
            p.start()
            self.addCleanup(p.stop)

    def test_head_sends_to_the_owner_of_the_plan(self):
        self.as_account(auth.Account('employee', 3, '부서장'))
        self.in_team()
        with patch.object(RT, 'send', return_value=[{'id': TID}]) as send:
            res = self.client.post(f'/api/v1/team/plans/{RID}/tasks', json={'body': '과제'})
        self.assertEqual((res.status_code, res.json()), (200, {'tasks': [{'id': TID}]}))
        send.assert_called_once_with(3, 8, RID, '과제')

    def test_file_is_downloaded_not_rendered(self):
        self.as_account(auth.Account('employee', 3, '부서장'))
        self.in_team()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'<script>')
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        with patch.object(RT, 'attachment_of', return_value=(Path(f.name), '결과 보고.html')) as of:
            res = self.client.get(f'/api/v1/team/plans/{RID}/tasks/{TID}/file')
        of.assert_called_once_with(8, RID, TID)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers['content-type'], 'application/octet-stream')
        self.assertEqual(res.headers['x-content-type-options'], 'nosniff')
        self.assertTrue(res.headers['content-disposition'].startswith("attachment; filename*=UTF-8''"))
        self.assertIn('%EA%B2%B0%EA%B3%BC', res.headers['content-disposition'])

    def test_member_submits_text_and_file(self):
        self.as_account(auth.Account('employee', 8, '직원'))
        with patch.object(RT, 'submit', return_value=[{'id': TID}]) as submit:
            res = self.client.post(f'/api/v1/plans/{RID}/tasks/{TID}/submit', data={'answer': '결과'}, files={'file': ('결과.txt', b'hello')})
        self.assertEqual(res.status_code, 200)
        submit.assert_called_once_with(8, RID, TID, '결과', '결과.txt', b'hello')
        with patch.object(RT, 'submit', return_value=[]) as submit:
            res = self.client.post(f'/api/v1/plans/{RID}/tasks/{TID}/submit', data={'answer': '글만'})
        self.assertEqual(res.status_code, 200)
        submit.assert_called_once_with(8, RID, TID, '글만', None, None)

    def test_member_cannot_read_a_file_of_someone_elses_plan(self):
        self.as_account(auth.Account('employee', 8, '직원'))
        with patch.object(work.PL, '_owned', side_effect=ApiError(404, 'NOT_FOUND', '없음')), patch.object(RT, 'attachment_of') as of:
            self.assertEqual(self.client.get(f'/api/v1/plans/{RID}/tasks/{TID}/file').status_code, 404)
        of.assert_not_called()


if __name__ == '__main__':
    unittest.main()
