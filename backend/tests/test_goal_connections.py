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

    def test_commit_failure_does_not_submit_job_and_releases_owner_once(self):
        events, connection = [], Mock()
        connection.execute.return_value.first.return_value = ('job',)
        owner = MagicMock()
        owner.__exit__.side_effect = lambda *args: events.append('owner-released')
        @contextmanager
        def begin():
            try:
                yield connection
                events.append('commit-failed')
                raise RuntimeError('commit failed')
            finally:
                events.append('connection-released')
        with patch.object(db.engine, 'begin', begin), \
             patch.object(generation_lock, 'generation_guard', return_value=owner), \
             patch.object(jobs.POOL, 'submit') as submit, patch.object(jobs, 'cancel') as cancel:
            with self.assertRaisesRegex(RuntimeError, 'commit failed'):
                with db.tx() as t:
                    self.assertEqual(jobs.start('goal-suggestions', 1, '1', Mock(_resume={}), transaction=t), 'job')
                    submit.assert_not_called()
                    owner.__exit__.assert_not_called()
            submit.assert_not_called()
            cancel.assert_not_called()
        owner.__exit__.assert_called_once_with(None, None, None)
        self.assertEqual(events, ['commit-failed', 'connection-released', 'owner-released'])

    def test_submit_failure_cancels_committed_job_and_releases_owner_once(self):
        events, connection = [], Mock()
        selected = SimpleNamespace(_mapping={'employee_id': 1, 'kind': 'goal-suggestions', 'status': 'running'})
        connection.execute.return_value.first.side_effect = [('job',), selected]
        owner = MagicMock()
        owner.__exit__.side_effect = lambda *args: events.append('owner-released')
        @contextmanager
        def begin():
            try:
                yield connection
                events.append('committed')
            finally:
                events.append('connection-released')
        def fail_submit(work):
            self.assertEqual(events, ['committed', 'connection-released'])
            events.append('submit-failed')
            raise RuntimeError('submit failed')
        with patch.object(db.engine, 'begin', begin), \
             patch.object(generation_lock, 'generation_guard', return_value=owner), \
             patch.object(jobs.POOL, 'submit', side_effect=fail_submit) as submit, \
             patch.object(jobs, 'cancel', wraps=jobs.cancel) as cancel:
            with self.assertRaisesRegex(RuntimeError, 'submit failed'):
                with db.tx() as t:
                    jobs.start('goal-suggestions', 1, '1', Mock(_resume={}), transaction=t)
                    submit.assert_not_called()
            submit.assert_called_once()
            cancel.assert_called_once_with('job', 1)
        statements = [str(item.args[0]) for item in connection.execute.call_args_list]
        self.assertEqual(len(statements), 3)
        self.assertIn('INSERT INTO app_ext.jobs', statements[0])
        self.assertIn('FOR UPDATE', statements[1])
        self.assertIn("SET status = 'cancelled'", statements[2])
        self.assertEqual(connection.execute.call_args_list[2].args[1], {'j': 'job'})
        owner.__exit__.assert_called_once_with(None, None, None)
        self.assertEqual(events, ['committed', 'connection-released', 'submit-failed',
                                  'committed', 'connection-released', 'owner-released'])

    def test_before_start_failure_rolls_back_without_submit_or_double_release(self):
        events, connection = [], Mock()
        connection.execute.return_value.first.return_value = ('job',)
        owner = MagicMock()
        @contextmanager
        def begin():
            try:
                yield connection
            except RuntimeError:
                events.append('rolled-back')
                raise
            else:
                events.append('committed')
            finally:
                events.append('connection-released')
        mark = Mock(side_effect=RuntimeError('mark failed'))
        with patch.object(db.engine, 'begin', begin), \
             patch.object(generation_lock, 'generation_guard', return_value=owner), \
             patch.object(jobs.POOL, 'submit') as submit, patch.object(jobs, 'cancel') as cancel:
            with self.assertRaisesRegex(RuntimeError, 'mark failed'):
                with db.tx() as t:
                    jobs.start('goal-suggestions', 1, '1', Mock(_resume={}), before_start=mark, transaction=t)
            mark.assert_called_once_with('job')
            submit.assert_not_called()
            cancel.assert_not_called()
        owner.__exit__.assert_called_once_with(None, None, None)
        self.assertEqual(events, ['rolled-back', 'connection-released'])
