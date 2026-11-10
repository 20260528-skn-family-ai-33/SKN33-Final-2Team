"""새 로드맵 확정의 시작 방식: 진행 중인 로드맵과 함께·끝난 다음 주부터·보관하고 이번 주부터(API-35)."""
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import roadmap as rm
from app.auth import Account, require_employee
from app.errors import ApiError, api_error_handler
from app.routers import work
from app.services import drafts, notifications as NT, plans

RID = '11111111-1111-1111-1111-111111111111'
TODAY = '2026-11-10'
api_app = FastAPI()
api_app.include_router(work.r)
api_app.add_exception_handler(ApiError, api_error_handler)


@contextmanager
def tx_of(t):
    yield t


def row(created: str, weeks: int, acts: list | None = None, start: str | None = None) -> dict:
    content = {'weeks': weeks, 'acts': acts or []}
    if start:
        content['startDate'] = start
    return {'status': 'IN_PROGRESS', 'project_id': created, 'roadmap_id': created, 'created_at': datetime.fromisoformat(created).replace(tzinfo=timezone.utc), 'content': content}


class NextStartTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(plans, 'today', return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_starts_the_week_after_the_last_week(self):
        self.assertEqual(plans.next_start([row('2026-11-04', 4)]), '2026-12-02')

    def test_follows_the_latest_ending_roadmap(self):
        self.assertEqual(plans.next_start([row('2026-11-04', 4), row('2026-11-09', 6)]), '2026-12-21')

    def test_activity_later_than_plan_weeks_extends_the_end(self):
        self.assertEqual(plans.next_start([row('2026-11-04', 2, [{'wTo': 5}])]), '2026-12-09')

    def test_counts_from_a_roadmap_already_scheduled_for_later(self):
        self.assertEqual(plans.next_start([row('2026-11-04', 2, start='2026-12-02')]), '2026-12-16')

    def test_no_delay_when_the_period_is_over_or_ends_today(self):
        self.assertIsNone(plans.next_start([row('2026-09-01', 2)]))
        self.assertIsNone(plans.next_start([row('2026-11-03', 1)]))

    def test_tomorrow_is_still_a_later_start(self):
        self.assertEqual(plans.next_start([row('2026-11-04', 1)]), '2026-11-11')

    def test_no_active_roadmap(self):
        self.assertIsNone(plans.next_start([]))


class ConfirmStartModeTests(unittest.TestCase):
    def confirm(self, mode, active=(), insert_error=None):
        option = {'id': 'A2', 'name': 'A2', 'short': 'A2', 'tagline': 'test', 'acts': []}
        w = {'draftPlan': {'exists': True}, 'draft': {'chosen': 'A2', 'gen': {'options': {'A2': option}}, 'handoff': {}, 'goal': 'test',
                                                      'quiz': {'questions': [], 'domain': 'test'}, 'answers': {}, 'prefs': {}}}
        self.t = Mock()
        self.t.all.return_value = []
        plan = {'opt': 'A2', 'acts': [], 'cost': 0, 'costUnknown': False}
        with ExitStack() as stack:
            self.tx = stack.enter_context(patch.object(drafts.db, 'tx', side_effect=lambda: tx_of(self.t)))
            stack.enter_context(patch.object(drafts, '_row', return_value={'draft_choices': w}))
            stack.enter_context(patch.object(drafts, '_wrap', side_effect=lambda x: x))
            stack.enter_context(patch.object(drafts, '_sync'))
            stack.enter_context(patch.object(rm, 'params_of', return_value={}))
            stack.enter_context(patch.object(rm, 'build_plan', return_value=plan))
            stack.enter_context(patch.object(drafts, 'deep_on', return_value=False))
            stack.enter_context(patch.object(drafts, '_round', return_value='round'))
            stack.enter_context(patch.object(plans, 'today', return_value=TODAY))
            stack.enter_context(patch.object(plans, 'shared_with', return_value={}))
            stack.enter_context(patch.object(NT, 'roadmap_created'))
            self.read_active = stack.enter_context(patch.object(plans, '_base_rows', return_value=list(active)))
            self.insert = stack.enter_context(patch.object(plans, 'insert_roadmap', return_value=RID, side_effect=insert_error))
            self.archive = stack.enter_context(patch.object(plans, 'archive_row'))
            return drafts.confirm(7, 'draft', mode)

    def saved_plan(self):
        return self.insert.call_args.args[3]

    def test_default_and_together_leave_active_roadmaps_alone(self):
        for mode in (None, 'together'):
            with self.subTest(mode=mode):
                self.assertEqual(self.confirm(mode, [row('2026-11-04', 4)])['planId'], RID)
                self.assertNotIn('startDate', self.saved_plan())
                self.read_active.assert_not_called()
                self.archive.assert_not_called()

    def test_after_saves_the_week_following_the_active_roadmaps(self):
        self.confirm('after', [row('2026-11-04', 4), row('2026-11-09', 6)])
        self.assertEqual(self.saved_plan()['startDate'], '2026-12-21')
        self.archive.assert_not_called()

    def test_after_with_finished_period_starts_now(self):
        self.confirm('after', [row('2026-09-01', 2)])
        self.assertNotIn('startDate', self.saved_plan())

    def test_archive_stores_every_active_roadmap_in_the_same_transaction(self):
        active = [row('2026-11-04', 4), row('2026-11-09', 6)]
        self.confirm('archive', active)
        self.assertEqual([c.args for c in self.archive.call_args_list], [(self.t, active[0]), (self.t, active[1])])
        self.assertNotIn('startDate', self.saved_plan())

    def test_only_in_progress_roadmaps_are_archived(self):
        done = dict(row('2026-10-01', 2), status='COMPLETED')
        archived = dict(row('2026-10-02', 2), status='ARCHIVED')
        active = row('2026-11-04', 4)
        self.confirm('archive', [done, archived, active])
        self.archive.assert_called_once_with(self.t, active)

    def test_nothing_is_archived_when_the_new_roadmap_cannot_be_saved(self):
        with self.assertRaises(RuntimeError):
            self.confirm('archive', [row('2026-11-04', 4)], insert_error=RuntimeError('db'))
        self.archive.assert_not_called()

    def test_unknown_mode_is_rejected_before_writing(self):
        with patch.object(drafts.db, 'tx') as tx:
            with self.assertRaises(ApiError) as caught:
                drafts.confirm(7, 'draft', 'later')
        self.assertEqual(caught.exception.status, 422)
        tx.assert_not_called()


class RouteTests(unittest.TestCase):
    URL = '/api/v1/drafts/draft/confirm'

    def setUp(self):
        api_app.dependency_overrides[require_employee] = lambda: Account('employee', 7, '시험')
        self.addCleanup(api_app.dependency_overrides.clear)
        self.client = TestClient(api_app)

    def test_passes_the_chosen_mode(self):
        with patch.object(work.DR, 'confirm', return_value={'planId': RID}) as confirm:
            self.assertEqual(self.client.post(self.URL, json={'startMode': 'after'}).status_code, 200)
        confirm.assert_called_once_with(7, 'draft', 'after')

    def test_request_without_a_body_still_confirms(self):
        with patch.object(work.DR, 'confirm', return_value={'planId': RID}) as confirm:
            self.assertEqual(self.client.post(self.URL).status_code, 200)
        confirm.assert_called_once_with(7, 'draft', None)

    def test_unknown_mode_answers_422(self):
        response = self.client.post(self.URL, json={'startMode': 'later'})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['error']['code'], 'BAD_START_MODE')


class AcceptRevisionTests(unittest.TestCase):
    def accept(self, current):
        pending = {'to': {'opt': 'A1', 'name': '계획', 'tagline': '요약', 'acts': []}, 'label': '주당 시간 변경', 'prefsTo': {}, 'handoff': {}}
        t = Mock()
        t.one.side_effect = [{'result': pending, 'status': 'ready'}, {'baseline_content': {}}]
        owned = {'roadmap_id': RID, 'content': dict(current, opt='A1', version=1)}
        with patch.object(plans.db, 'tx', side_effect=lambda: tx_of(t)), patch.object(plans.db, 'J', side_effect=lambda x: x), \
                patch.object(plans, '_owned', return_value=owned), patch.object(plans, 'validate_free_plan'), \
                patch.object(plans, '_write_steps'), patch.object(plans, 'record', return_value={}):
            plans.accept_revision(7, RID, 'rev')
        return next(c.kwargs['c'] for c in t.run.call_args_list if 'UPDATE public.roadmaps' in c.args[0])

    def test_scheduled_start_survives_a_revision(self):
        self.assertEqual(self.accept({'startDate': '2026-12-02'})['startDate'], '2026-12-02')

    def test_roadmap_without_a_scheduled_start_stays_without_one(self):
        self.assertNotIn('startDate', self.accept({}))


if __name__ == '__main__':
    unittest.main()
