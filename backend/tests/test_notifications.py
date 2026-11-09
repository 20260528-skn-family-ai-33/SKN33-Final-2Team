"""알림(#82·#96): 로드맵 확정·보고서 저장과 같은 트랜잭션에서 남기는지, 실패하면 남기지 않는지, 작업 완료·코멘트 알림 규칙, 알림 API 권한·응답 모양을 검사한다.
받는 사람을 고르는 SQL(본인·같은 부서 부서장)은 실제 PostgreSQL 이 있어야 해서 이 단위 검사에 넣지 않았다(PR 검증 기록 참고)."""
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import inspect
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, jobs
from app.agents import roadmap as rm
from app.errors import AgentError, ApiError, api_error_handler
from app.routers import notifications as api
from app.services import drafts, notifications as NT, plans

RID = '11111111-1111-1111-1111-111111111111'
NID = '22222222-2222-2222-2222-222222222222'
DID = '33333333-3333-3333-3333-333333333333'
CID = '44444444-4444-4444-4444-444444444444'


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
    def test_roadmap_goes_to_heads_only_and_report_to_owner_and_heads(self):
        t = Mock()
        NT.roadmap_created(t, 7, RID)
        NT.report_created(t, 7, RID, NID)
        (roadmap_sql, ), kw = t.run.call_args_list[0]
        self.assertIn(NT.HEAD_SEES, roadmap_sql)
        self.assertIn("'head'", roadmap_sql)
        self.assertNotIn("'self'", roadmap_sql)  # 본인이 직접 누른 확정은 본인에게 알리지 않는다(#96)
        self.assertEqual(kw, {'e': 7, 'k': 'roadmap', 'r': RID, 'rep': None})
        (report_sql, ), kw = t.run.call_args_list[1]
        self.assertIn(NT.HEAD_SEES, report_sql)
        self.assertIn("'self'", report_sql)
        self.assertIn("'head'", report_sql)
        self.assertEqual(kw, {'e': 7, 'k': 'report', 'r': RID, 'rep': NID})

    def test_inbox_shape(self):
        at = datetime(2026, 11, 4, 9, 30, tzinfo=timezone.utc)
        empty = {'draft_id': None, 'comment_id': None, 'job_kind': None, 'job_status': None}
        rows = [dict(empty, notification_id=NID, kind='report', audience='head', actor_id=8, actor_name='김직원', roadmap_id=RID,
                     report_id=NID, created_at=at, read_at=None, plan_title='SQL 분석', track='A2'),
                dict(empty, notification_id=RID, kind='roadmap', audience='self', actor_id=7, actor_name='나', roadmap_id=RID,
                     report_id=None, created_at=at, read_at=at, plan_title=None, track=None),
                dict(empty, notification_id=CID, kind='job', audience='self', actor_id=7, actor_name='나', roadmap_id=None, report_id=None,
                     created_at=at, read_at=None, plan_title='목표', track=None, draft_id=DID, job_kind='options', job_status='failed'),
                dict(empty, notification_id=CID, kind='comment', audience='member', actor_id=3, actor_name='부서장', roadmap_id=RID, report_id=None,
                     created_at=at, read_at=None, plan_title='SQL 분석', track='A2', comment_id=CID)]
        with patch.object(NT.db, 'all_', return_value=rows) as q, patch.object(NT.db, 'val', return_value=3):
            out = NT.inbox(7)
        sql = q.call_args.args[0]
        self.assertIn(NT.HEAD_SEES, sql)  # 부서 이동한 직원의 알림은 부서장에게 보이지 않게 거른다
        self.assertIn("n.audience IN ('self', 'member')", sql)
        self.assertIn('LEFT JOIN public.roadmaps r', sql)  # 로드맵 확정 전 작업 알림도 나와야 한다
        self.assertIn('n.read_at IS NULL', sql)  # 읽은 알림은 목록에서 뺀다(#96)
        self.assertEqual(out['unread'], 3)
        self.assertEqual(out['items'][0], {'id': NID, 'kind': 'report', 'audience': 'head', 'employee': {'id': '8', 'name': '김직원'}, 'planId': RID,
                                           'planTitle': 'SQL 분석', 'track': 'A2', 'reportId': NID, 'draftId': None, 'commentId': None,
                                           'jobKind': None, 'jobStatus': None, 'createdAt': at.isoformat(), 'read': False})
        self.assertEqual((out['items'][1]['reportId'], out['items'][1]['read'], out['items'][1]['planTitle']), (None, True, ''))
        self.assertEqual((out['items'][2]['planId'], out['items'][2]['draftId'], out['items'][2]['jobKind'], out['items'][2]['jobStatus']), (None, DID, 'options', 'failed'))
        self.assertEqual((out['items'][3]['audience'], out['items'][3]['commentId'], out['items'][3]['employee']), ('member', CID, {'id': '3', 'name': '부서장'}))

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


class JobFinishedTests(unittest.TestCase):
    """백그라운드 작업 완료·실패 알림(#96): 오래 걸리는 생성만, 본인에게, 나뉜 작업은 모두 끝났을 때 한 번"""

    def finish(self, kind, ref, status, rows=(), resume=None):
        t = Mock()
        t.all.return_value = [{'status': s} for s in rows]
        with patch.object(NT.db, 'tx', side_effect=lambda: tx_of(t)) as tx:
            NT.job_finished(kind, 7, ref, status, resume)
        return t, tx

    @staticmethod
    def inserted(t):
        return [c.kwargs for c in t.run.call_args_list if 'INSERT' in c.args[0]]

    def test_options_wait_until_every_proposal_is_finished(self):
        t, _ = self.finish('option', f'{DID}:A1', 'done', ['done', 'running', 'done'])
        self.assertEqual(self.inserted(t), [])

    def test_options_notify_once_all_are_done_replacing_the_unread_result(self):
        t, _ = self.finish('option', f'{DID}:A3', 'done', ['done', 'done', 'done'])
        self.assertEqual(self.inserted(t), [{'e': 7, 'r': None, 'd': DID, 'g': 'options', 's': 'done'}])
        sql = [c.args[0] for c in t.run.call_args_list]
        self.assertIn('DELETE', sql[0])
        self.assertIn('read_at IS NULL', sql[0])  # 이미 읽은 지난 알림은 건드리지 않는다
        self.assertIn('INSERT', sql[1])
        self.assertIn('pg_advisory_xact_lock', t.val.call_args.args[0])  # 동시에 끝나도 한 건만 남게 순서를 세운다

    def test_options_report_failure_when_any_proposal_failed(self):
        t, _ = self.finish('option', f'{DID}:A3', 'done', ['done', 'failed', 'done'])
        self.assertEqual(self.inserted(t)[0]['s'], 'failed')

    def test_only_the_latest_job_of_each_proposal_counts(self):
        t, _ = self.finish('option', f'{DID}:A3', 'done', ['done'])
        sql = t.all.call_args.args[0]
        self.assertIn('DISTINCT ON', sql)
        self.assertIn('created_at DESC', sql)
        self.assertEqual(t.all.call_args.kwargs['p'], f'{DID}:%')

    def test_regenerate_revision_targets(self):
        t, _ = self.finish('regenerate', f'{DID}:A2', 'failed')
        self.assertEqual(self.inserted(t), [{'e': 7, 'r': None, 'd': DID, 'g': 'regenerate', 's': 'failed'}])
        t, _ = self.finish('revision', RID, 'done')
        self.assertEqual(self.inserted(t), [{'e': 7, 'r': RID, 'd': None, 'g': 'revision', 's': 'done'}])

    def test_report_notifies_only_on_failure(self):
        # 성공은 보고서 저장과 함께 report_created 가 남긴다
        _, tx = self.finish('report', RID, 'done')
        tx.assert_not_called()
        t, _ = self.finish('report', RID, 'failed')
        self.assertEqual(self.inserted(t), [{'e': 7, 'r': RID, 'd': None, 'g': 'report', 's': 'failed'}])

    def test_learning_materials_are_told_apart_by_resume_info(self):
        t, _ = self.finish('learning_generation', f'{DID}:A1:key', 'done', ['done'], {'operation': 'materials'})
        self.assertEqual(self.inserted(t)[0]['g'], 'materials')
        t, _ = self.finish('learning_generation', DID, 'done', [], {'operation': 'route', 'function': 'generate_recommendations'})
        self.assertEqual(self.inserted(t)[0]['d'], DID)
        t, _ = self.finish('learning_generation', DID, 'done', ['running'], {'operation': 'route', 'function': 'generate_recommendations'})
        self.assertEqual(self.inserted(t), [])  # 코스별 준비 작업이 남아 있으면 마지막 작업이 알린다
        _, tx = self.finish('learning_generation', DID, 'done', [], {'operation': 'route', 'function': 'propose_activities'})
        tx.assert_not_called()

    def test_other_jobs_and_malformed_refs_do_not_notify(self):
        for kind, ref in (('assistant', 'q'), ('assessment', DID), ('diagnosis', DID), ('doc-summary', DID), ('support', DID), ('revision', 'not-a-uuid'), ('option', None)):
            _, tx = self.finish(kind, ref, 'done')
            tx.assert_not_called()


class JobRunnerHookTests(unittest.TestCase):
    """작업 상태를 저장한 뒤에만 알리고, 알림 실패가 작업 결과를 바꾸지 않는다"""

    def run_job(self, work, changed=1, side_effect=None, resume=None):
        t = Mock()
        t.val.return_value = 'job-1'
        t.run.return_value = changed
        if resume:
            work._resume = resume
        with ExitStack() as stack:
            stack.enter_context(patch.object(jobs.db, 'tx', side_effect=lambda: tx_of(t)))
            stack.enter_context(patch.object(jobs.db, 'val', return_value='running'))
            stack.enter_context(patch.object(jobs.db, 'J', side_effect=lambda v: v))
            stack.enter_context(patch.object(jobs.POOL, 'submit', side_effect=lambda f: f()))
            notify = stack.enter_context(patch.object(NT, 'job_finished', side_effect=side_effect))
            if resume:
                stack.enter_context(patch('app.services.generation_lock.generation_guard', return_value=MagicMock()))
            jobs.start('revision', 7, RID, work)
        return notify, t

    def test_success_and_failure_notify_after_status_is_saved(self):
        notify, t = self.run_job(lambda _: {'ok': True})
        notify.assert_called_once_with('revision', 7, RID, 'done', None)
        self.assertIn('UPDATE app_ext.jobs', t.run.call_args.args[0])

        def boom(_):
            raise AgentError('Ollama 연결 실패')
        notify, _ = self.run_job(boom)
        notify.assert_called_once_with('revision', 7, RID, 'failed', None)

    def test_resume_info_reaches_the_notification(self):
        def work(_):
            return {}
        notify, _ = self.run_job(work, resume={'operation': 'materials'})
        self.assertEqual(notify.call_args.args[-1], {'operation': 'materials'})

    def test_user_stopped_or_cancelled_jobs_do_not_notify(self):
        def stopped(_):
            raise AgentError('멈춤', stopped=True)
        notify, _ = self.run_job(stopped)
        notify.assert_not_called()
        notify, _ = self.run_job(lambda _: {}, changed=0)  # 그사이 사용자가 취소해 상태가 바뀌지 않음
        notify.assert_not_called()

    def test_notification_failure_is_logged_and_does_not_break_the_job(self):
        with self.assertLogs('app.jobs', level='ERROR') as logs:
            notify, _ = self.run_job(lambda _: {}, side_effect=RuntimeError('표 없음'))
        notify.assert_called_once()
        self.assertIn('job-1', logs.output[0])


class CommentHookTests(unittest.TestCase):
    """부서장 코멘트 알림(#96): 새 코멘트만 그 직원에게. 고칠 때와 로드맵 수정안 확정은 알리지 않는다"""

    FIELDS = {'fit': 'a', 'fitText': '', 'level': 'b', 'levelText': '', 'free': '새 내용'}

    def with_comment(self, t, fn):
        with ExitStack() as stack:
            stack.enter_context(patch.object(plans, '_comment_target', return_value={'roadmap_id': RID}))
            stack.enter_context(patch.object(plans, '_comment_fields', return_value=self.FIELDS))
            stack.enter_context(patch.object(plans, '_comment_body', return_value='본문'))
            stack.enter_context(patch.object(plans.db, 'tx', side_effect=lambda: tx_of(t)))
            notify = stack.enter_context(patch.object(NT, 'comment_sent'))
            return fn(), notify

    def test_new_comment_notifies_the_member_in_the_same_transaction(self):
        t = Mock()
        t.val.return_value = CID
        out, notify = self.with_comment(t, lambda: plans.send_comment(3, 8, RID, {}))
        self.assertEqual(out, CID)
        notify.assert_called_once_with(t, 3, 8, RID, CID)

    def test_edit_does_not_notify(self):
        t = Mock()
        t.one.side_effect = [{'author_employee_id': 3}, {'fit': 'x', 'fit_text': '', 'level': 'y', 'level_text': '', 'free_text': '', 'status': 'new'}]
        _, notify = self.with_comment(t, lambda: plans.edit_comment(3, 8, RID, CID, {}))
        notify.assert_not_called()

    def test_insert_addresses_the_member_with_the_head_as_actor(self):
        t = Mock()
        NT.comment_sent(t, 3, 8, RID, CID)
        (sql, ), kw = t.run.call_args
        self.assertIn("'comment', 'member'", sql)
        self.assertEqual(kw, {'m': 8, 'h': 3, 'r': RID, 'c': CID})

    def test_accepting_a_revision_does_not_notify_the_head(self):
        self.assertNotIn('NT.', inspect.getsource(plans.accept_revision))


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
