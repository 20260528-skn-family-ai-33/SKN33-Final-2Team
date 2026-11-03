from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier, Lock
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, MagicMock, patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from app.errors import ApiError
from app.services import generation_lock as locks, generation_job


class MemorySessions:
    """독립 연결의 PostgreSQL 세션 잠금 계약을 모의한다."""
    def __init__(self):
        self.held = set()
        self.mutex = Lock()

    @contextmanager
    def connect(self):
        held_here = set()
        def execute(sql, params):
            key = params['key']
            with self.mutex:
                if 'pg_try_advisory_lock' in str(sql):
                    result = key not in self.held
                    if result: self.held.add(key); held_here.add(key)
                else:
                    result = key in held_here
                    self.held.discard(key); held_here.discard(key)
            return SimpleNamespace(scalar=lambda: result)
        try:
            yield SimpleNamespace(execution_options=lambda **kw: None, execute=execute)
        finally:
            with self.mutex: self.held.difference_update(held_here)


class GenerationConcurrencyTests(TestCase):
    def setUp(self):
        self.memory = MemorySessions()
        # 컨텍스트 연결 자체를 반환한다.
        original = self.memory.connect
        @contextmanager
        def connect():
            # 가드가 사용하는 SQLAlchemy 인터페이스만 모의한다.
            with original() as conn:
                conn.execution_options = lambda **kw: conn
                yield conn
        patcher = patch.object(locks.lock_engine, 'connect', side_effect=connect)
        patcher.start(); self.addCleanup(patcher.stop)

    def test_different_projects_generate_at_the_same_time(self):
        barrier = Barrier(2)
        def generate(identifier):
            with locks.generation_guard('draft', identifier):
                barrier.wait(timeout=3)
                return identifier
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(generate, 'project-a')
            second = pool.submit(generate, 'project-b')
            self.assertEqual({first.result(timeout=4), second.result(timeout=4)}, {'project-a', 'project-b'})
        self.assertFalse(self.memory.held)

    def test_same_draft_cross_operation_is_rejected_before_generation(self):
        model = Mock()
        with locks.generation_guard('draft', 'same-project'):
            with self.assertRaises(ApiError) as error:
                with locks.generation_guard('draft', 'same-project'): model()
        self.assertEqual(error.exception.code, 'GENERATION_BUSY')
        model.assert_not_called()

    def test_failure_releases_lock_for_retry(self):
        with self.assertRaises(ValueError):
            with locks.generation_guard('draft', 'project'): raise ValueError('model failed')
        with locks.generation_guard('draft', 'project'): pass
        self.assertFalse(self.memory.held)

    def test_roadmap_and_draft_scopes_are_separate(self):
        with locks.generation_guard('draft', 'same-id'):
            with locks.generation_guard('roadmap', 'same-id'): pass
        self.assertEqual(locks.lock_key('draft', 'x'), locks.lock_key('draft', 'x'))


class GenerationJobTests(TestCase):
    def setUp(self):
        self.calls = []
        app = FastAPI()
        @app.post('/generate/{project_id}')
        @generation_job.queued_generation
        def generate(project_id: str, a: str = 'test'):
            self.calls.append(project_id)
            return {'project': project_id}
        self.app = app
        self.client = TestClient(app)

    def test_async_endpoint_returns_job_without_running_model(self):
        # 실제 API는 require_employee 의 Account를 주입한다. 래퍼 자체의 작업 계약 검증.
        from app.auth import Account
        account = Account('employee', 7, 'test')
        request = Request({'type': 'http', 'headers': [(b'prefer', b'respond-async')]})
        run = Mock(return_value={'done': True})
        @generation_job.queued_generation
        def endpoint(project_id, a): return run()
        with patch.object(generation_job.jobs, 'start', return_value='job-id') as start:
            response = endpoint('project', account, generation_request=request)
        self.assertEqual(response.status_code, 202)
        run.assert_not_called()
        self.assertEqual(start.call_args.args[1:3], (7, 'project'))
        self.assertEqual(start.call_args.args[3](None), {'done': True})
        run.assert_called_once()

    def test_http_async_request_injects_request_and_returns_202(self):
        from fastapi import Depends
        from app.auth import Account
        app = FastAPI()
        run = Mock(return_value={'done': True})
        def account(): return Account('employee', 7, 'test')
        @app.post('/generate/{project_id}')
        @generation_job.queued_generation
        def endpoint(project_id: str, a=Depends(account)):
            return run()
        with patch.object(generation_job.jobs, 'start', return_value='http-job') as start:
            response = TestClient(app).post('/generate/project', headers={'Prefer': 'respond-async'})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['jobId'], 'http-job')
        self.assertEqual(start.call_args.args[1:3], (7, 'project'))
        run.assert_not_called()
        self.assertEqual(start.call_args.args[3](None), {'done': True})

    def test_legacy_sync_response_still_works(self):
        response = self.client.post('/generate/project')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'project': 'project'})

    def test_validation_errors_are_saved_as_explicit_job_failures(self):
        from app.auth import Account
        request = Request({'type': 'http', 'headers': [(b'prefer', b'respond-async')]})
        @generation_job.queued_generation
        def endpoint(project_id, a): raise ValueError('invalid materials')
        with patch.object(generation_job.jobs, 'start', return_value='job') as start:
            endpoint('project', Account('employee', 7, 'test'), generation_request=request)
        with self.assertRaises(ApiError) as error: start.call_args.args[3](None)
        self.assertEqual(error.exception.code, 'GENERATION_INVALID')


class GenerationJobOwnershipTests(TestCase):
    def fake_tx(self, tx):
        @contextmanager
        def begin():
            yield tx
        return begin

    def test_server_start_preserves_live_generation_and_marks_only_lost_one(self):
        from app import jobs
        tx = Mock()
        tx.run.return_value = 1
        tx.all.return_value = [{'job_id': 'live'}, {'job_id': 'lost'}]
        tx.val.side_effect = [False, True]
        with patch.object(jobs.db, 'tx', side_effect=self.fake_tx(tx)):
            self.assertEqual(jobs.mark_lost(), 2)  # one legacy row and one lost generation
        updates = [call.kwargs.get('j') for call in tx.run.call_args_list if 'j' in call.kwargs]
        self.assertEqual(updates, ['lost'])
        self.assertIn("kind <> 'learning_generation'", tx.run.call_args_list[0].args[0])

    def test_queued_generation_owns_session_until_result_saved(self):
        from app import jobs
        tx = Mock(); tx.val.return_value = 'job'
        lease = MagicMock()
        generate = Mock(return_value={'ok': True})
        with patch.object(jobs.db, 'tx', side_effect=self.fake_tx(tx)), \
             patch.object(jobs.db, 'val', return_value='running'), \
             patch.object(locks, 'generation_guard', return_value=lease), \
             patch.object(jobs.POOL, 'submit') as submit:
            jobs.start('learning_generation', 1, 'project', generate)
            lease.__enter__.assert_called_once()
            lease.__exit__.assert_not_called()
            submit.call_args.args[0]()
        generate.assert_called_once()
        lease.__exit__.assert_called_once()

    def test_cancelled_queued_generation_skips_model_and_releases_owner(self):
        from app import jobs
        tx = Mock(); tx.val.return_value = 'job'
        lease = MagicMock()
        generate = Mock()
        with patch.object(jobs.db, 'tx', side_effect=self.fake_tx(tx)), \
             patch.object(jobs.db, 'val', return_value='cancelled'), \
             patch.object(locks, 'generation_guard', return_value=lease), \
             patch.object(jobs.POOL, 'submit') as submit:
            jobs.start('learning_generation', 1, 'project', generate)
            submit.call_args.args[0]()
        generate.assert_not_called()
        lease.__exit__.assert_called_once()

    def test_submit_failure_cancels_job_and_releases_owner(self):
        from app import jobs
        tx = Mock(); tx.val.return_value = 'job'
        lease = MagicMock()
        with patch.object(jobs.db, 'tx', side_effect=self.fake_tx(tx)), \
             patch.object(locks, 'generation_guard', return_value=lease), \
             patch.object(jobs.POOL, 'submit', side_effect=RuntimeError('pool unavailable')), \
             patch.object(jobs, 'cancel') as cancel:
            with self.assertRaises(RuntimeError): jobs.start('learning_generation', 1, 'project', Mock())
        cancel.assert_called_once_with('job', 1)
        lease.__exit__.assert_called_once()
