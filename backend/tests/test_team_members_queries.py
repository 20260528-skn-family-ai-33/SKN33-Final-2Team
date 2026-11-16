"""#290: 부서장 소속 직원 목록을 직원별 반복 조회 없이 만들고, 세션 확인이 매 요청 쓰기를 하지 않는지 검사한다.
실제 DB에서 이전 결과와 같은지는 PR 검증 기록(로컬 복원 DB 비교)으로 확인했다."""
from contextlib import contextmanager
import unittest
from unittest.mock import Mock, patch

from app import auth
from app.services import plans, profile


def emp(i, dept=1, head=False, **kw):
    return {'employee_id': i, 'employee_number': f'E{i}', 'name': f'직원{i}', 'department_id': dept, 'is_department_head': head,
            'dept': '개발팀', 'parent_dept': '본부', 'grade': '선임', 'position': '팀원', 'source_type': 'TEAM', 'hire_date': None,
            'job': None, 'job_family': None, 'task': None, 'employee_group': None, 'employment_status': None, 'account_status': None,
            'valid_from': None, 'change_reason': None, 'grade_since': None, **kw}


class TeamRowTests(unittest.TestCase):
    def test_team_row_matches_team_view_of_full_view(self):
        rows = [emp(1, head=True, position='팀장'), emp(2), emp(3, dept=2, head=True), emp(4, dept=None)]
        src = {'present': False, 'workDesc': None, 'expSummary': None, 'devYears': None, 'inputStatus': {}, **{k: [] for k in profile.LISTS}}
        with patch.object(profile, '_self_of', return_value=(src, False, None)), patch.object(profile.db, 'all_', return_value=[]):
            for r in rows:
                with self.subTest(employee=r['employee_id']):
                    self.assertEqual(profile.team_row(r, rows), profile.team_view(profile.view(r['employee_id'], rows)))
                    self.assertEqual(profile.sup_group(r), profile.view(r['employee_id'], rows)['supGroup'])


class TeamMembersTests(unittest.TestCase):
    def run_members(self, rows, counts):
        q = Mock(return_value=counts)
        with patch.object(plans.profile, '_rows', return_value=rows), patch.object(plans.db, 'all_', q), \
             patch.object(plans.NT, 'unseen_counts', return_value={}), \
             patch.object(plans, 'records', side_effect=AssertionError('직원별 기록 조립 금지')), \
             patch.object(plans, 'reports', side_effect=AssertionError('직원별 보고서 조립 금지')), \
             patch.object(plans.profile, 'view', side_effect=AssertionError('직원별 본인 입력 조회 금지')):
            return plans.team_members(1), q

    def test_counts_all_members_in_one_query(self):
        rows = [emp(1, head=True), emp(2), emp(3), emp(9, dept=2)]
        out, q = self.run_members(rows, [{'employee_id': 2, 'active': 2, 'past': 1, 'reports': 3, 'unread': 4}])
        self.assertEqual(q.call_count, 1)
        self.assertEqual(q.call_args.kwargs['ids'], [2, 3])
        self.assertEqual(out['group'], {'name': '개발팀', 'id': '1'})
        got = {m['user']['id']: (m['activePlans'], m['pastPlans'], m['reports'], m['unreadComments']) for m in out['members']}
        self.assertEqual(got, {'2': (2, 1, 3, 4), '3': (0, 0, 0, 0)})

    def test_head_without_members_skips_count_query(self):
        out, q = self.run_members([emp(1, head=True), emp(9, dept=2)], [])
        self.assertEqual(out, {'group': {'name': '개발팀', 'id': '1'}, 'members': []})
        q.assert_not_called()

    def test_count_sql_keeps_records_and_reports_conditions(self):
        q = Mock(return_value=[])
        with patch.object(plans.db, 'all_', q):
            plans._member_counts([2])
        sql = ' '.join(q.call_args.args[0].split())
        for part in ("p.status = 'IN_PROGRESS'", "p.status IN ('COMPLETED', 'ARCHIVED')", "r.content ? 'acts' AND r.content ? 'opt'",
                     "g.report_content ? 'gained'", "coalesce(m.status, 'new') = 'new'", "m.fit IS DISTINCT FROM '__deleted__'"):
            self.assertIn(part, sql)
        self.assertNotIn('post_checks', sql)


class AccountOfTests(unittest.TestCase):
    def call(self, session, account):
        t = Mock()
        t.one.side_effect = [session, account]

        @contextmanager
        def tx():
            yield t
        request = Mock(cookies={auth.COOKIE: 'token'})
        with patch.object(auth.db, 'tx', tx):
            return auth.account_of(request), t

    def test_recent_session_does_not_write(self):
        a, t = self.call({'account_type': 'employee', 'account_id': 5, 'stale': False}, {'employee_id': 5, 'name': '가', 'acc': 'active', 'st': '재직'})
        self.assertEqual(a, auth.Account('employee', 5, '가'))
        t.run.assert_not_called()
        self.assertTrue(t.one.call_args_list[0].args[0].lstrip().startswith('SELECT'))
        self.assertIn('expires_at > now()', t.one.call_args_list[0].args[0])

    def test_stale_session_refreshes_last_seen(self):
        a, t = self.call({'account_type': 'admin', 'account_id': 1, 'stale': True}, {'admin_id': 1, 'name': '관리자'})
        self.assertEqual(a, auth.Account('admin', 1, '관리자'))
        sql = t.run.call_args.args[0]
        self.assertIn('UPDATE app_ext.sessions SET last_seen_at = now()', sql)
        self.assertIn(f"interval '{auth.SEEN_REFRESH_MINUTES} minutes'", sql)

    def test_expired_inactive_and_retired_accounts_are_blocked(self):
        cases = [(None, None), ({'account_type': 'admin', 'account_id': 1, 'stale': False}, None),
                 ({'account_type': 'employee', 'account_id': 5, 'stale': False}, {'employee_id': 5, 'name': '가', 'acc': 'inactive', 'st': '재직'}),
                 ({'account_type': 'employee', 'account_id': 5, 'stale': False}, {'employee_id': 5, 'name': '가', 'acc': 'active', 'st': '퇴직'})]
        for session, account in cases:
            with self.subTest(session=session, account=account):
                self.assertIsNone(self.call(session, account)[0])


if __name__ == '__main__':
    unittest.main()
