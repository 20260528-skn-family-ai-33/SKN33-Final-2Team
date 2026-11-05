"""트랜잭션 완료 전 worker 시작과 중첩 풀 연결 회귀 방지."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')
from contextlib import contextmanager, nullcontext
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BoundedSemaphore, Lock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, MagicMock, patch
from app import db, jobs
from app.services import goals, generation_lock


class GoalConnectionTests(unittest.TestCase):
    def test_sixteen_requests_with_saturated_pool(self):
        pool, barrier = BoundedSemaphore(16), Barrier(16)
        person = {'dept': '개발', 'job': '개발자', 'profile': {'workDesc': 'API 개발'}, 'projects': ['검색']}
        @contextmanager
        def transaction():
            if not pool.acquire(timeout=1):
                raise TimeoutError('nested connection exhausted pool')
            t = Mock(after_commit=[], after_rollback=[])
            t.one.return_value = {}
            t.val.return_value = 'job'
            try:
                barrier.wait(timeout=5)
                yield t
            finally:
                pool.release()
            for callback in t.after_commit:
                callback()
        def view(employee_id, *, t=None):
            self.assertIsNotNone(t)
            return person
        with patch.object(db, 'tx', transaction), patch.object(goals.profile, 'view', side_effect=view), patch.object(goals, '_run_state'), patch.object(generation_lock, 'generation_guard', side_effect=lambda *args: nullcontext()), patch.object(jobs.POOL, 'submit') as submit:
            with ThreadPoolExecutor(max_workers=16) as workers:
                results = list(workers.map(lambda eid: goals.request(eid, 'self-input', only_if_stale=True), range(16)))
            self.assertEqual(results, ['job'] * 16)
            self.assertEqual(submit.call_count, 16)

    def test_running_job_reuses_transaction(self):
        t = Mock()
        t.one.return_value = {'status': 'running', 'job_id': 'existing'}
        with patch.object(db, 'tx', return_value=nullcontext(t)), patch.object(jobs, 'alive', return_value={'existing'}) as alive, patch.object(goals, '_request') as start:
            self.assertEqual(goals.request(1, 'self-input'), 'existing')
            alive.assert_called_once_with(['existing'], t)
            start.assert_not_called()

    def test_job_is_submitted_only_after_commit_and_lock_released_on_rollback(self):
        for rollback in (False, True):
            with self.subTest(rollback=rollback):
                t = db.Tx(Mock())
                t.val = Mock(return_value='job')
                owner = MagicMock()
                work = Mock(_resume={})
                with patch.object(generation_lock, 'generation_guard', return_value=owner), patch.object(jobs.POOL, 'submit') as submit, patch.object(db, 'tx', side_effect=AssertionError('nested connection')):
                    jobs.start('goal-suggestions', 1, '1', work, transaction=t)
                    submit.assert_not_called()
                    for callback in (t.after_rollback if rollback else t.after_commit):
                        callback()
                    self.assertEqual(submit.call_count, 0 if rollback else 1)
                    self.assertEqual(owner.__exit__.call_count, 1 if rollback else 0)

    def test_db_callbacks_run_after_connection_release(self):
        events = []
        @contextmanager
        def begin():
            try:
                yield Mock()
            finally:
                events.append('released')
        with patch.object(db.engine, 'begin', begin):
            with db.tx() as t:
                t.after_commit.append(lambda: events.append('submitted'))
        self.assertEqual(events, ['released', 'submitted'])

