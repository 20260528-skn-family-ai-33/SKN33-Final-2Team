from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.errors import ApiError
from app.services import drafts, plans


class CrashRequirementJobStateTests(unittest.TestCase):
    def setUp(self):
        self.work = None
        self.tx = Mock()
        self.job = SimpleNamespace(job_id='job')
        self.error_code = 'SKILLS_INVALID'
        self.note = '주 2시간으로 바꿔 주세요'
        self.enterContext(patch.object(drafts.jobs, 'start', side_effect=self.start))
        self.enterContext(patch.object(drafts.rt, 'context', return_value=Mock(fail_sim={})))

    def start(self, kind, employee, ref, work, *, before_start=None):
        if before_start:
            before_start(self.job.job_id)
        self.work = work
        return self.job.job_id

    def draft_state(self, state):
        def mutate(employee, draft, fn):
            fn(self.tx, state)
            return state
        self.enterContext(patch.object(drafts, '_mutate', side_effect=mutate))
        self.enterContext(patch.object(drafts.RM, 'option', side_effect=self.check_input))

    @staticmethod
    def check_input(ctx, inp, **kwargs):
        raise ApiError(422, 'SKILLS_INVALID', '선정 스킬 이름을 확인해 주세요.')

    def test_option_error_remains_visible_after_job_finishes(self):
        rows = {pid: {'st': 'fail', 'tries': 0} for pid in drafts.D['optionOrder']}
        state = {'draft': {'handoff': {'goal': self.note}, 'genRun': {'key': 'k', 'rows': rows}}}
        self.draft_state(state)
        drafts._run_option(1, 'draft', 'A2')
        with self.assertRaises(ApiError) as caught:
            self.work(self.job)
        drafts._heal(self.tx, state)
        self.assertEqual((rows['A2']['st'], rows['A2']['jobId']), ('fail', None))
        self.assertEqual(rows['A2']['err']['code'], self.error_code)
        self.assertEqual(rows['A2']['err']['user'], caught.exception.message)

    def test_regeneration_failure_preserves_previous_option_and_reason(self):
        option = {'id': 'A2', 'acts': [], 'tagline': '기존 안'}
        gen = {'key': 'k', 'options': {'A2': deepcopy(option)}}
        state = {'draft': {'handoff': {}, 'gen': gen}}
        self.draft_state(state)
        with patch.object(drafts, 'present', return_value={}):
            drafts.regenerate(1, 'draft', 'A2', {'wish': self.note})
        with self.assertRaises(ApiError):
            self.work(self.job)
        drafts._heal(self.tx, state)
        self.assertEqual(gen['regenErr']['A2']['code'], self.error_code)
        self.assertNotIn('A2', gen['regenRun'])
        self.assertEqual(gen['options']['A2'], option)

    def test_revision_uses_current_constraints_and_persists_input_failure(self):
        for change, expected in [(True, []), (False, ['Django 필수'])]:
            with self.subTest(change=change):
                original = {'goal': 'API 구현', 'details': {'etc': 'Django 필수', 'goalType': 'api'},
                            'userNotes': ['Django 필수']}
                base = {'handoff': deepcopy(original), 'opt': 'A2', 'start': 1, 'acts': [], 'prefs': {'etc': 'Django 필수'}}
                row = {'roadmap_id': 'rid', 'status': 'IN_PROGRESS', 'content': base}
                actual = {}
                def revise(ctx, inp, **kwargs):
                    actual.update(inp)
                    return self.check_input(ctx, inp)
                with patch.object(plans, '_owned', return_value=row), patch.object(plans.db, 'all_', return_value=[]), \
                     patch.object(plans.db, 'tx', side_effect=lambda: nullcontext(self.tx)), \
                     patch.object(plans.rt, 'sim_once', return_value=None), patch.object(plans.RM, 'revise', side_effect=revise):
                    opts = {'on': {'etc': change}, 'v': {'etc': ''}, 'note': self.note}
                    plans.revise_start(1, 'rid', {'rev': opts})
                    with self.assertRaises(ApiError):
                        self.work(self.job)
                self.assertEqual(self.tx.run.call_args.kwargs['e'].obj['cause']['code'], self.error_code)
                self.assertEqual(actual['handoff']['userNotes'], expected)
                self.assertEqual(actual['handoff']['details']['etc'], 'Django 필수' if expected else '')
                self.assertEqual(actual['handoff']['details']['goalType'], 'api')
                self.assertEqual(base['handoff'], original)
