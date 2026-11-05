"""완료 알림(#82): 로드맵 확정·보고서 저장과 같은 트랜잭션에서 남기는지, 실패하면 남기지 않는지, 알림 API 권한·응답 모양을 검사한다.
받는 사람을 고르는 SQL(본인·같은 부서 부서장)은 실제 PostgreSQL 이 있어야 해서 이 단위 검사에 넣지 않았다(PR 검증 기록 참고)."""
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth
from app.agents import roadmap as rm
from app.errors import AgentError, ApiError, api_error_handler
from app.routers import notifications as api
from app.services import drafts, notifications as NT, plans

RID = '11111111-1111-1111-1111-111111111111'
NID = '22222222-2222-2222-2222-222222222222'


@contextmanager
def tx_of(t):
    yield t


class ConfirmHookTests(unittest.TestCase):
    """로드맵 생성 완료 = 검토·확정의 '확정'(drafts.confirm)"""

    def confirm(self, pid, cost):
        option = {'id': pid, 'name': pid, 'short': pid, 'tagline': 'test', 'acts': []}
        w = {'draftPlan': {'exists': True}, 'draft': {'chosen': pid, 'gen': {'options': {pid: option}}, 'handoff': {}, 'goal': 'test',
                                                      'quiz': {'questions': [], 'domain': 'test'}, 'answers': {}, 'prefs': {}}}
        t = Mock()
        t.all.return_value = [{'resource_key': 'free', 'cost_won': cost}]
        plan = {'opt': pid, 'acts': [{'res': 'free'}], 'cost': 100, 'costUnknown': True}
        with ExitStack() as stack:
            stack.enter_context(patch.object(drafts.db, 'tx', side_effect=lambda: tx_of(t)))
            stack.enter_context(patch.object(drafts, '_row', return_value={'draft_choices': w}))
            stack.enter_context(patch.object(drafts, '_wrap', side_effect=lambda x: x))
            stack.enter_context(patch.object(drafts, '_sync'))
            stack.enter_context(patch.object(rm, 'params_of', return_value={}))
            stack.enter_context(patch.object(rm, 'build_plan', return_value=plan))
            stack.enter_context(patch.object(drafts, 'deep_on', return_value=False))
            stack.enter_context(patch.object(drafts, '_round', return_value='round'))
            stack.enter_context(patch.object(plans, 'insert_roadmap', return_value=RID))
            stack.enter_context(patch.object(plans, 'shared_with', return_value={}))
            notify = stack.enter_context(patch.object(NT, 'roadmap_created'))
            try:
                return drafts.confirm(7, 'draft'), notify, t
            except ApiError as e:
                return e, notify, t

    def test_confirm_notifies_in_the_same_transaction(self):
        out, notify, t = self.confirm('A2', 100)
        self.assertEqual(out['planId'], RID)
        notify.assert_called_once_with(t, 7, RID)

    def test_rejected_confirm_leaves_no_notification(self):
        # Free 트랙(A1)에 유료 자료가 있으면 저장 전에 막는다 → 알림도 없다
        out, notify, _ = self.confirm('A1', 100)
        self.assertIsInstance(out, ApiError)
        notify.assert_not_called()


class ReportHookTests(unittest.TestCase):
    """보고서 작성 완료 = 사후 점검 뒤 보고서 작성 작업이 보고서를 저장한 때(확인 전)"""

    def start(self, report):
        assess = {'domain': 'SQL', 'questions': [{'id': 'q1', 'area': 'SQL', 'skill': 'SQL', 'text': '조인을 작성할 수 있다.'}], 'answers': {'q1': '1'}}
        plan = {'version': 1, 'goal': '분석', 'name': '계획', 'opt': 'A1', 'acts': [], 'assess': assess}
        post = {'answers': {'q1': '4'}, 'goalSelf': '1'}
        row = {'roadmap_id': RID, 'project_id': 1, 'diagnostic_round_id': 1, 'content': plan}
        t = Mock()
        t.one.return_value = None
        t.val.return_value = 'report-1'
        with ExitStack() as stack:
            stack.enter_context(patch.object(plans, '_owned', return_value=row))
            stack.enter_context(patch.object(plans, 'record', return_value={'plan': plan, 'post': post, 'progress': {}}))
            stack.enter_context(patch.object(plans, '_report_deep', return_value=None))
            stack.enter_context(patch.object(plans.db, 'one', return_value={}))
            stack.enter_context(patch.object(plans.db, 'val', return_value={}))
            stack.enter_context(patch.object(plans.db, 'J', side_effect=lambda v: v))
            stack.enter_context(patch.object(plans.db, 'tx', side_effect=lambda: tx_of(t)))
            stack.enter_context(patch.object(plans.rt, 'context', return_value=Mock()))
            stack.enter_context(patch.object(plans.rt, 'sim_once', return_value=None))
            stack.enter_context(patch.object(plans.DG, 'report', **report))
            stack.enter_context(patch.object(plans.DG, 'level_of', return_value={}))
            stack.enter_context(patch.object(plans.jobs, 'start', side_effect=lambda kind, e, ref, work: work(SimpleNamespace(job_id='j')) and 'j'))
            notify = stack.enter_context(patch.object(NT, 'report_created'))
            try:
                plans.report_start(7, RID)
            except AgentError:
                pass
        return notify, t

    def test_saved_report_notifies_in_the_same_transaction(self):
        notify, t = self.start({'return_value': {'good': [], 'improve': [], 'next': None}})
        notify.assert_called_once_with(t, 7, RID, 'report-1')

    def test_failed_report_leaves_no_notification(self):
        notify, t = self.start({'side_effect': AgentError('Ollama 연결 실패')})
        notify.assert_not_called()
        self.assertFalse(any('growth_reports' in str(c.args[0]) for c in t.val.call_args_list if c.args))


class ServiceTests(unittest.TestCase):
    def test_insert_targets_owner_and_same_department_heads(self):
        t = Mock()
        NT.roadmap_created(t, 7, RID)
        NT.report_created(t, 7, RID, NID)
        (sql, ), kw = t.run.call_args_list[0]
        self.assertIn(NT.HEAD_SEES, sql)
        self.assertIn("'self'", sql)
        self.assertIn("'head'", sql)
        self.assertEqual(kw, {'e': 7, 'k': 'roadmap', 'r': RID, 'rep': None})
        self.assertEqual(t.run.call_args_list[1].kwargs, {'e': 7, 'k': 'report', 'r': RID, 'rep': NID})

    def test_inbox_shape(self):
        at = datetime(2026, 11, 4, 9, 30, tzinfo=timezone.utc)
        rows = [{'notification_id': NID, 'kind': 'report', 'audience': 'head', 'actor_id': 8, 'actor_name': '김직원', 'roadmap_id': RID,
                 'report_id': NID, 'created_at': at, 'read_at': None, 'plan_title': 'SQL 분석', 'track': 'A2'},
                {'notification_id': RID, 'kind': 'roadmap', 'audience': 'self', 'actor_id': 7, 'actor_name': '나', 'roadmap_id': RID,
                 'report_id': None, 'created_at': at, 'read_at': at, 'plan_title': None, 'track': None}]
        with patch.object(NT.db, 'all_', return_value=rows) as q, patch.object(NT.db, 'val', return_value=3):
            out = NT.inbox(7)
        self.assertIn(NT.HEAD_SEES, q.call_args.args[0])  # 부서 이동한 직원의 알림은 부서장에게 보이지 않게 거른다
        self.assertEqual(out['unread'], 3)
        self.assertEqual(out['items'][0], {'id': NID, 'kind': 'report', 'audience': 'head', 'employee': {'id': '8', 'name': '김직원'}, 'planId': RID,
                                           'planTitle': 'SQL 분석', 'track': 'A2', 'reportId': NID, 'createdAt': at.isoformat(), 'read': False})
        self.assertEqual((out['items'][1]['reportId'], out['items'][1]['read'], out['items'][1]['planTitle']), (None, True, ''))

    def test_read_rejects_malformed_and_foreign_ids(self):
        with patch.object(NT.db, 'tx') as tx:
            with self.assertRaises(ApiError) as e:
                NT.read(7, 'not-a-uuid')
            self.assertEqual(e.exception.status, 404)
            tx.assert_not_called()
        t = Mock()
        t.run.return_value = 0  # 받는 사람이 다르면 UPDATE 0행
        with patch.object(NT.db, 'tx', side_effect=lambda: tx_of(t)):
            with self.assertRaises(ApiError) as e:
                NT.read(7, NID)
        self.assertEqual(e.exception.status, 404)
        self.assertEqual(t.run.call_args.kwargs, {'i': NID, 'e': 7})


class UnseenTests(unittest.TestCase):
    """부서장의 확인 전 로드맵·보고서(#96): 아직 읽지 않은 소속 직원 알림을 대상 기준으로 센다"""

    def test_unseen_counts_by_member(self):
        rows = [{'actor_id': 8, 'plans': 2, 'reports': 1}, {'actor_id': 9, 'plans': 0, 'reports': None}]
        with patch.object(NT.db, 'all_', return_value=rows) as q:
            out = NT.unseen_counts(7)
        sql = q.call_args.args[0]
        self.assertIn(NT.HEAD_SEES, sql)  # 부서를 옮긴 직원의 알림은 세지 않는다
        self.assertIn('read_at IS NULL', sql)
        self.assertIn("n.audience = 'head'", sql)
        self.assertIn('count(DISTINCT n.roadmap_id)', sql)  # 같은 대상의 알림이 여럿이어도 1개로
        self.assertEqual(q.call_args.kwargs, {'e': 7})
        self.assertEqual(out, {8: {'plans': 2, 'reports': 1}, 9: {'plans': 0, 'reports': 0}})

    def test_unseen_targets_of_one_member(self):
        rows = [{'kind': 'roadmap', 'roadmap_id': RID, 'report_id': None}, {'kind': 'report', 'roadmap_id': RID, 'report_id': NID}]
        with patch.object(NT.db, 'all_', return_value=rows) as q:
            out = NT.unseen_targets(7, 8)
        self.assertEqual(q.call_args.kwargs, {'h': 7, 'm': 8})
        self.assertIn('read_at IS NULL', q.call_args.args[0])
        self.assertEqual(out, {'plans': [RID], 'reports': [NID]})

    def test_read_target_rejects_bad_kind_and_id(self):
        with patch.object(NT.db, 'tx') as tx:
            with self.assertRaises(ApiError) as e:
                NT.read_target(7, 'comment', RID)
            self.assertEqual(e.exception.status, 400)
            with self.assertRaises(ApiError) as e:
                NT.read_target(7, 'roadmap', 'not-a-uuid')
            self.assertEqual(e.exception.status, 404)
            tx.assert_not_called()

    def test_read_target_marks_only_that_target_of_mine(self):
        empty = {'items': [], 'unread': 0}
        for kind, col, n in (('roadmap', 'n.roadmap_id', 2), ('report', 'n.report_id', 0)):
            t = Mock()
            t.run.return_value = n
            with patch.object(NT.db, 'tx', side_effect=lambda: tx_of(t)), patch.object(NT, 'inbox', return_value=empty):
                out = NT.read_target(7, kind, NID)
            sql = t.run.call_args.args[0]
            self.assertIn(f'{col} = CAST(:i AS uuid)', sql)
            self.assertIn('n.recipient_id = :e', sql)  # 내 알림만
            self.assertEqual(t.run.call_args.kwargs, {'e': 7, 'k': kind, 'i': NID})
            self.assertEqual(out, {'items': [], 'unread': 0, 'changed': n})  # 읽을 알림이 없어도 오류가 아니다


class TeamUnseenTests(unittest.TestCase):
    """소속 직원 목록·직원 기록 응답에 확인 전 수와 대상 id 가 실리는지(#96)"""

    def test_team_members_carry_unseen_counts(self):
        rows = [{'employee_id': 8}, {'employee_id': 9}, {'employee_id': 10}]
        with ExitStack() as stack:
            stack.enter_context(patch.object(plans.profile, 'view', side_effect=lambda i, *_: {'id': i, 'supGroup': None}))
            stack.enter_context(patch.object(plans.profile, 'member_ids', return_value={8, 9}))
            stack.enter_context(patch.object(plans.profile, '_rows', return_value=rows))
            stack.enter_context(patch.object(plans.profile, 'team_view', side_effect=lambda v: {'id': str(v['id'])}))
            stack.enter_context(patch.object(plans, 'records', return_value={}))
            stack.enter_context(patch.object(plans, 'reports', return_value=[]))
            stack.enter_context(patch.object(NT, 'unseen_counts', return_value={8: {'plans': 1, 'reports': 2}}))
            out = plans.team_members(7)
        got = {m['user']['id']: (m['unseenPlans'], m['unseenReports']) for m in out['members']}
        self.assertEqual(got, {'8': (1, 2), '9': (0, 0)})

    def test_member_state_carries_unseen_targets(self):
        unseen = {'plans': [RID], 'reports': []}
        with ExitStack() as stack:
            stack.enter_context(patch.object(plans.profile, 'member_ids', return_value={8}))
            stack.enter_context(patch.object(plans.profile, 'view', return_value={'id': 8}))
            stack.enter_context(patch.object(plans.profile, 'team_view', return_value={'id': '8'}))
            stack.enter_context(patch.object(plans, 'records', return_value={}))
            stack.enter_context(patch.object(plans, 'reports', return_value=[]))
            stack.enter_context(patch.object(plans, 'resources_of', return_value={}))
            stack.enter_context(patch.object(plans, 'reg_of', return_value={}))
            q = stack.enter_context(patch.object(NT, 'unseen_targets', return_value=unseen))
            out = plans.member_state(7, 8)
        q.assert_called_once_with(7, 8)
        self.assertEqual(out['unseen'], unseen)


class ApiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(api.r)
        app.add_exception_handler(ApiError, api_error_handler)
        self.client = TestClient(app)

    def as_account(self, account):
        p = patch.object(auth, 'account_of', return_value=account)
        p.start()
        self.addCleanup(p.stop)

    def test_admin_and_anonymous_cannot_use_notifications(self):
        self.as_account(None)
        self.assertEqual(self.client.get('/api/v1/notifications').status_code, 401)
        self.as_account(auth.Account('admin', 1, '관리자'))
        for method, path in (('get', ''), ('post', '/read-all'), ('post', f'/{NID}/read')):
            self.assertEqual(getattr(self.client, method)('/api/v1/notifications' + path).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/notifications/read-target', json={'kind': 'roadmap', 'id': RID}).status_code, 403)

    def test_employee_reads_own_notifications(self):
        self.as_account(auth.Account('employee', 7, '시험'))
        empty = {'items': [], 'unread': 0}
        with patch.object(NT, 'inbox', return_value=empty) as inbox, patch.object(NT, 'read', return_value=empty) as read, \
                patch.object(NT, 'read_all', return_value=empty) as read_all:
            self.assertEqual(self.client.get('/api/v1/notifications').json(), empty)
            self.client.post(f'/api/v1/notifications/{NID}/read')
            self.client.post('/api/v1/notifications/read-all')
        inbox.assert_called_once_with(7)
        read.assert_called_once_with(7, NID)
        read_all.assert_called_once_with(7)

    def test_employee_marks_a_target_read(self):
        self.as_account(auth.Account('employee', 7, '시험'))
        with patch.object(NT, 'read_target', return_value={'items': [], 'unread': 0, 'changed': 1}) as read_target:
            res = self.client.post('/api/v1/notifications/read-target', json={'kind': 'report', 'id': NID})
        self.assertEqual(res.json()['changed'], 1)
        read_target.assert_called_once_with(7, 'report', NID)


if __name__ == '__main__':
    unittest.main()
