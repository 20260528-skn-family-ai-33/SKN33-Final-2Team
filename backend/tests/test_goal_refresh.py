"""목표 후보 교체·실패 보존·입력 변경을 실제 DB/모델 없이 검증한다."""
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.services import goals
from app.errors import AgentError


class GoalRefreshTests(unittest.TestCase):
    def setUp(self):
        self.person = {'dept': '개발팀', 'job': '개발자', 'profile': {'workDesc': 'API 개발'}, 'projects': ['검색 프로젝트']}
        self.candidates = [{'goal': text, 'why': '업무 근거', 'basis': ['업무 설명']} for text in ['검색을 배우고 싶어요.', '운영을 배우고 싶어요.', '분석을 배우고 싶어요.']]

    def test_invalid_candidates_do_not_delete_previous_rows(self):
        for rows in [self.candidates[:2], self.candidates + self.candidates[:1], [self.candidates[0]] * 3]:
            transaction = Mock()
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                goals._save(transaction, 1, rows)
            transaction.run.assert_not_called()

    def test_missing_candidate_is_repaired_but_complete_cache_is_reused(self):
        for count in [2, 3]:
            transaction = Mock()
            transaction.one.return_value = {'status': 'ready', 'profile_hash': goals._hash(goals.G.goal_input(self.person))}
            transaction.val.return_value = count
            with patch.object(goals.db, 'tx') as tx, patch.object(goals.profile, 'view', return_value=self.person), patch.object(goals, '_request', return_value='new') as start:
                tx.return_value.__enter__.return_value = transaction
                result = goals.request(1, 'self-input', only_if_stale=True)
            self.assertEqual(start.call_count, int(count != 3))
            self.assertEqual(result, 'new' if count != 3 else None)

    def run_worker(self, *, changed=False, failure=False):
        transaction = Mock()
        transaction.one.return_value = {'job_id': 'job'}
        latest = dict(self.person, projects=['변경된 프로젝트']) if changed else self.person
        captured = {}
        with ExitStack() as stack:
            tx = stack.enter_context(patch.object(goals.db, 'tx'))
            tx.return_value.__enter__.return_value = transaction
            stack.enter_context(patch.object(goals.profile, 'view', side_effect=[self.person, latest]))
            stack.enter_context(patch.object(goals.rt, 'context', return_value=SimpleNamespace(mode='mock')))
            stack.enter_context(patch.object(goals.rt, 'sim_once', return_value=None))
            model = stack.enter_context(patch.object(goals.G, 'run', return_value={'candidates': self.candidates}))
            if failure:
                model.side_effect = AgentError({'user': '생성 실패'})
            save = stack.enter_context(patch.object(goals, '_save'))
            stack.enter_context(patch.object(goals, '_run_state'))
            follow = stack.enter_context(patch.object(goals, 'request', return_value='new-job'))
            def start(kind, employee_id, ref, work, **kwargs):
                captured['work'] = work
                return 'job'
            stack.enter_context(patch.object(goals.jobs, 'start', side_effect=start))
            goals._request(1, 'self-input', None, None)
            save.assert_not_called()  # 생성 시작만으로 기존 후보를 지우지 않는다.
            if failure:
                with self.assertRaises(AgentError):
                    captured['work'](SimpleNamespace(job_id='job'))
            else:
                captured['work'](SimpleNamespace(job_id='job'))
            return save.call_count, follow.call_count, model.call_args.args[1]

    def test_success_replaces_candidates_with_both_personal_inputs(self):
        saves, follows, payload = self.run_worker()
        self.assertEqual((saves, follows), (1, 0))
        self.assertEqual(payload['profile']['workDescription'], 'API 개발')
        self.assertEqual(payload['profile']['projects'], ['검색 프로젝트'])

    def test_failure_keeps_previous_candidates(self):
        saves, follows, _ = self.run_worker(failure=True)
        self.assertEqual((saves, follows), (0, 0))

    def test_changed_input_discards_old_result_and_prepares_new_input(self):
        saves, follows, _ = self.run_worker(changed=True)
        self.assertEqual((saves, follows), (0, 1))

    def test_changed_input_is_prepared_even_when_old_generation_fails(self):
        saves, follows, _ = self.run_worker(changed=True, failure=True)
        self.assertEqual((saves, follows), (0, 1))
