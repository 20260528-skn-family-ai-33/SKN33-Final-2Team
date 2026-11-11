import copy
import unittest
from unittest.mock import Mock, patch

from app.errors import ApiError
from app.services import drafts


class OptionRecoveryTests(unittest.TestCase):
    def state(self, rows=None):
        d = drafts.fresh_draft()
        d.update(handoff={'key': 'h'}, genRun={'key': 'h', 'rows': rows or {
            p: {'st': 'fail', 'out': None, 'jobId': None, 'tries': 0} for p in drafts.D['optionOrder']}})
        d['diag'] = {'key': drafts.diag_key(d)}
        return {'draft': d, 'draftPlan': None}

    def mutate(self, w):
        def run(employee, draft, fn):
            result = fn(Mock(), w)
            return w if result is None else result
        return run

    def start_options(self, w, live=()):
        with patch.object(drafts, '_mutate', side_effect=self.mutate(w)), \
             patch.object(drafts.jobs, 'alive', return_value=set(live)), \
             patch.object(drafts.PF, 'view', return_value={}), \
             patch.object(drafts.DG, 'work_profile', return_value={}), \
             patch.object(drafts, 'build_handoff', return_value={'key': 'h'}), \
             patch.object(drafts, '_round', return_value='round'), \
             patch.object(drafts, 'present', side_effect=lambda state, _: state), \
             patch.object(drafts, '_run_option', return_value='new-job') as start:
            drafts.options_start(1, 'draft')
            return start

    def test_running_request_does_not_reset_or_duplicate(self):
        w = self.state()
        for p, row in w['draft']['genRun']['rows'].items():
            row.update(st='run', jobId=p, tries=1)
        before = copy.deepcopy(w)
        start = self.start_options(w, drafts.D['optionOrder'])
        start.assert_not_called()
        self.assertEqual(w['draft']['genRun'], before['draft']['genRun'])

    def test_retry_starts_only_failed_and_lost_preserving_success(self):
        w = self.state()
        rows = w['draft']['genRun']['rows']
        rows['A1'].update(st='ok', out={'id': 'A1'})
        rows['A2'].update(st='run', jobId='ended')
        rows['A3'].update(st='run', jobId=None)
        start = self.start_options(w)
        self.assertEqual([c.args[2] for c in start.call_args_list], ['A2', 'A3'])
        self.assertEqual(rows['A1']['out'], {'id': 'A1'})

    def test_heal_preserves_live_and_fails_missing_or_ended_jobs(self):
        w = self.state()
        for p, row in w['draft']['genRun']['rows'].items():
            row.update(st='run', jobId={'A1': 'live', 'A2': 'ended', 'A3': None}[p])
        with patch.object(drafts.jobs, 'alive', return_value={'live'}):
            drafts._heal(Mock(), w)
        self.assertEqual([r['st'] for r in w['draft']['genRun']['rows'].values()], ['run', 'fail', 'fail'])

    def test_get_heals_legacy_rows_without_any_job_ids(self):
        w = self.state()
        w['draft']['genRun']['rows']['A2']['st'] = 'run'
        with patch.object(drafts, '_mutate', side_effect=self.mutate(w)) as mutate, \
             patch.object(drafts.jobs, 'alive', return_value=set()):
            drafts._healed(1, 'draft', w)
        mutate.assert_called_once()
        self.assertEqual(w['draft']['genRun']['rows']['A2']['st'], 'fail')

    def test_partial_accept_heals_orphan_and_keeps_success(self):
        w = self.state()
        rows = w['draft']['genRun']['rows']
        rows['A1'].update(st='ok', out={'id': 'A1'})
        rows['A2'].update(st='run', jobId=None)
        with patch.object(drafts, '_mutate', side_effect=self.mutate(w)), \
             patch.object(drafts.jobs, 'alive', return_value=set()), \
             patch.object(drafts, 'present', side_effect=lambda state, _: state):
            drafts.accept_partial(1, 'draft')
        self.assertEqual(w['draft']['gen']['options'], {'A1': {'id': 'A1'}})
        self.assertEqual(w['draft']['gen']['missing'], ['A2', 'A3'])

    def test_option_retry_heals_ended_job_before_check(self):
        w = self.state()
        w['draft']['genRun']['rows']['A2'].update(st='run', jobId='ended')
        with patch.object(drafts, '_mutate', side_effect=self.mutate(w)), \
             patch.object(drafts.jobs, 'alive', return_value=set()), \
             patch.object(drafts, '_run_option', return_value='new-job') as start, \
             patch.object(drafts, 'get', return_value={}):
            result = drafts.option_retry(1, 'draft', 'A2')
        start.assert_called_once_with(1, 'draft', 'A2', expected_key='h')
        self.assertEqual(result['jobs'], {'A2': 'new-job'})

    def test_job_id_is_saved_before_worker_and_duplicate_start_rejected(self):
        w = self.state()
        workers = []
        def start(kind, employee, ref, work, *, before_start):
            before_start('job-' + str(len(workers)))
            workers.append(work)
            return 'job-0'
        with patch.object(drafts, '_mutate', side_effect=self.mutate(w)), \
             patch.object(drafts.jobs, 'alive', return_value={'job-0'}), \
             patch.object(drafts.jobs, 'start', side_effect=start):
            drafts._run_option(1, 'draft', 'A2')
            self.assertEqual(w['draft']['genRun']['rows']['A2']['jobId'], 'job-0')
            with self.assertRaises(ApiError) as caught:
                drafts._run_option(1, 'draft', 'A2')
        self.assertEqual(caught.exception.code, 'OPTION_RUNNING')
        self.assertEqual(len(workers), 1)

    def test_submit_failure_becomes_retryable_and_retry_succeeds(self):
        w = self.state()
        def rejected(kind, employee, ref, work, *, before_start):
            before_start('failed-job')
            raise RuntimeError('executor unavailable')
        def accepted(kind, employee, ref, work, *, before_start):
            before_start('retry-job')
            return 'retry-job'
        with patch.object(drafts, '_mutate', side_effect=self.mutate(w)), \
             patch.object(drafts.jobs, 'alive', return_value=set()):
            with patch.object(drafts.jobs, 'start', side_effect=rejected):
                with self.assertRaises(RuntimeError): drafts._run_option(1, 'draft', 'A2')
            row = w['draft']['genRun']['rows']['A2']
            self.assertEqual(row['st'], 'fail')
            self.assertIsNone(row['jobId'])
            with patch.object(drafts.jobs, 'start', side_effect=accepted):
                self.assertEqual(drafts._run_option(1, 'draft', 'A2'), 'retry-job')
            self.assertEqual(row['tries'], 2)

    def test_old_worker_cannot_overwrite_replacement(self):
        w = self.state()
        workers = []
        def start(kind, employee, ref, work, *, before_start):
            before_start('old-job')
            workers.append(work)
            return 'old-job'
        with patch.object(drafts, '_mutate', side_effect=self.mutate(w)), \
             patch.object(drafts.jobs, 'start', side_effect=start):
            drafts._run_option(1, 'draft', 'A2')
        row = w['draft']['genRun']['rows']['A2']
        row.update(jobId='new-job', tries=2)
        with patch.object(drafts, '_mutate', side_effect=self.mutate(w)), \
             patch.object(drafts.rt, 'context', return_value=Mock(provider='openai', fail_sim={})), \
             patch.object(drafts.RM, 'option', return_value={'id': 'old-result'}):
            workers[0](Mock(job_id='old-job'))
        self.assertEqual(row['jobId'], 'new-job')
        self.assertIsNone(row['out'])

    def test_changed_input_rejects_queued_start(self):
        w = self.state()
        def start(kind, employee, ref, work, *, before_start): before_start('job')
        with patch.object(drafts, '_mutate', side_effect=self.mutate(w)), \
             patch.object(drafts.jobs, 'start', side_effect=start):
            with self.assertRaises(ApiError) as caught:
                drafts._run_option(1, 'draft', 'A2', expected_key='old-key')
        self.assertEqual(caught.exception.code, 'STALE_RUN')

    def test_two_simultaneous_retries_start_one_worker(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier, Lock
        w = self.state()
        barrier, row_lock, jobs_lock = Barrier(2), Lock(), Lock()
        live, workers = set(), []
        def mutate(employee, draft, fn):
            with row_lock:
                result = fn(Mock(), w)
                return w if result is None else result
        def start(kind, employee, ref, work, *, before_start):
            with jobs_lock:
                jid = 'job-' + str(len(live))
                live.add(jid)
            barrier.wait(timeout=5)
            before_start(jid)
            workers.append(work)
            return jid
        def retry():
            try: return drafts._run_option(1, 'draft', 'A2')
            except ApiError as error: return error.code
        with patch.object(drafts, '_mutate', side_effect=mutate), \
             patch.object(drafts.jobs, 'alive', side_effect=lambda ids, t: set(ids) & live), \
             patch.object(drafts.jobs, 'start', side_effect=start), \
             ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: retry(), range(2)))
        self.assertEqual(len(workers), 1)
        self.assertIn('OPTION_RUNNING', results)
        self.assertEqual(w['draft']['genRun']['rows']['A2']['tries'], 1)

    def test_first_start_creates_three_retryable_rows_and_starts_all(self):
        w = self.state()
        w['draft']['genRun'] = None
        start = self.start_options(w)
        self.assertEqual([c.args[2] for c in start.call_args_list], drafts.D['optionOrder'])
        self.assertFalse(drafts._orphaned_options(w))

    def test_retry_keeps_a_different_live_course_running(self):
        w = self.state()
        rows = w['draft']['genRun']['rows']
        rows['A1'].update(st='ok', out={'id': 'A1'})
        rows['A2'].update(st='run', jobId='live')
        start = self.start_options(w, ['live'])
        self.assertEqual([c.args[2] for c in start.call_args_list], ['A3'])
        self.assertEqual(rows['A2']['st'], 'run')

    def test_partial_retry_preserves_selected_plan_and_materials(self):
        w = self.state()
        rows = w['draft']['genRun']['rows']
        rows['A1'].update(st='ok', out={'id': 'A1'})
        rows['A3'].update(st='ok', out={'id': 'A3'})
        w['draft'].update(chosen='A1', gen={'key': 'h', 'options': {'A1': rows['A1']['out'], 'A3': rows['A3']['out']}, 'missing': ['A2']})
        w['draftPlan'] = {'opt': 'A1', 'acts': [{'id': 'keep'}]}
        w['courseRecommendations'] = {'A1': {'selectedBooks': ['book'], 'selectedCourses': ['course']}}
        before = copy.deepcopy(w)
        start = self.start_options(w)
        self.assertEqual([c.args[2] for c in start.call_args_list], ['A2'])
        for field in ('gen', 'chosen'):
            self.assertEqual(w['draft'][field], before['draft'][field])
        self.assertEqual(w['draftPlan'], before['draftPlan'])
        self.assertEqual(w['courseRecommendations'], before['courseRecommendations'])

    def test_job_registration_failure_leaves_no_running_row(self):
        w = self.state()
        with patch.object(drafts.jobs, 'start', side_effect=RuntimeError('registration failed')):
            with self.assertRaises(RuntimeError): drafts._run_option(1, 'draft', 'A2')
        row = w['draft']['genRun']['rows']['A2']
        self.assertEqual(row['st'], 'fail')
        self.assertIsNone(row['jobId'])
