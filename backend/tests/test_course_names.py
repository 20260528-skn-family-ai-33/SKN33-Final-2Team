"""코스 이름 통일(#78): 공식 이름 Free·Crash·Challenge Course, 보고서 opt 는 코스 ID, 이전 Track 이름 호환."""
from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.agents import roadmap as RM
from app.agents.demo import D, course_id, course_name
from app.services import drafts, plans

OFFICIAL = {'A1': 'Free Course', 'A2': 'Crash Course', 'A3': 'Challenge Course'}
LEGACY = {'A1': 'Free Track', 'A2': 'Fast Track', 'A3': 'Challenge Track'}


class CourseNameTests(unittest.TestCase):
    def test_official_names_are_course_and_crash(self):
        self.assertEqual({k: v['name'] for k, v in D['perspectives'].items()}, OFFICIAL)
        self.assertEqual(D['perspectives']['A2']['short'], 'Crash')

    def test_ids_current_and_legacy_names_map_to_the_same_course(self):
        for pid in OFFICIAL:
            for value in (pid, OFFICIAL[pid], LEGACY[pid]):
                with self.subTest(value=value):
                    self.assertEqual(course_id(value), pid)
                    self.assertEqual(course_name(value), OFFICIAL[pid])

    def test_unknown_or_empty_values_are_not_guessed(self):
        self.assertEqual(course_id('가상 코스'), '가상 코스')
        self.assertEqual(course_name('가상 코스', '대체 이름'), '대체 이름')
        self.assertEqual(course_id(None), '')
        self.assertEqual(course_name('', ''), '')


class StoredPlanNameTests(unittest.TestCase):
    def test_revision_request_and_model_inputs_use_official_name_for_old_plans(self):
        with patch.object(drafts, 'cert_res', return_value=None):
            changes = plans._rev_changes({'v': {'pid': 'A2'}, 'on': {'pid': True}}, {'opt': 'A1', 'acts': [], 'prefs': {}, 'start': 1})
        self.assertEqual(changes['c']['perspective'], 'A2 Crash Course')
        selection = drafts.selection_of({'id': 'A2', 'name': 'Fast Track'})
        self.assertEqual((selection['name'], selection['agent']), ('Crash Course', '로드맵 계획 에이전트 · A2 Crash Course'))
        with patch.object(drafts.catalog, 'items', return_value={}):
            support = drafts._sup_input('A3', 'Challenge Track', {'acts': [], 'weeks': 4, 'hours': 3, 'cost': 0})
        self.assertEqual(support['name'], 'A3 Challenge Course')
        old = {'opt': 'A1', 'name': 'Free Track', 'goal': 'g', 'hours': 3, 'cost': 0}
        with patch.object(drafts.PL, 'records', return_value={'p': {'plan': old}}):
            self.assertEqual(drafts._plans_brief(1)[0]['name'], 'Free Course')

    def test_rebuilt_plan_from_old_option_gets_official_name(self):
        option = {'id': 'A2', 'name': 'Fast Track', 'short': 'Fast', 'tagline': 't', 'acts': []}
        with patch('app.services.duration_proposals.apply_plan_schedule', side_effect=lambda plan: plan):
            plan = RM.build_plan(option, {'start': 1, 'hours': 3, 'format': 'online', 'patch': {}}, '목표')
        self.assertEqual((plan['opt'], plan['name']), ('A2', 'Crash Course'))


class ReportCourseTests(unittest.TestCase):
    def _run_report(self, plan: dict) -> tuple[dict, dict]:
        post = {'answers': {'q1': '4'}, 'goalSelf': '1'}
        assess = {'domain': 'SQL', 'questions': [{'id': 'q1', 'area': 'SQL', 'skill': 'SQL', 'text': '조인을 작성할 수 있다.'}], 'answers': {'q1': '2'}}
        plan = dict(plan, version=2, goal='분석', acts=[], assess=assess)
        row = {'roadmap_id': 'p', 'project_id': 1, 'diagnostic_round_id': 1, 'content': plan}
        transaction = Mock()
        transaction.one.return_value = None
        transaction.val.return_value = 'report'
        model = Mock(return_value={'good': [], 'improve': [], 'next': None})
        with ExitStack() as stack:
            stack.enter_context(patch.object(plans, '_owned', return_value=row))
            stack.enter_context(patch.object(plans, 'record', return_value={'plan': plan, 'post': post, 'progress': {}}))
            stack.enter_context(patch.object(plans, '_report_deep', return_value=None))
            stack.enter_context(patch.object(plans.db, 'one', return_value={}))
            stack.enter_context(patch.object(plans.db, 'val', return_value={}))
            stack.enter_context(patch.object(plans.db, 'J', side_effect=lambda value: value))
            tx = stack.enter_context(patch.object(plans.db, 'tx'))
            tx.return_value.__enter__.return_value = transaction
            stack.enter_context(patch.object(plans.rt, 'context', return_value=Mock()))
            stack.enter_context(patch.object(plans.rt, 'sim_once', return_value=None))
            stack.enter_context(patch.object(plans.DG, 'report', model))
            stack.enter_context(patch.object(plans.DG, 'level_of', return_value={}))
            stack.enter_context(patch.object(plans.NT, 'report_created'))
            stack.enter_context(patch.object(plans.jobs, 'start', side_effect=lambda kind, employee, ref, work: work(SimpleNamespace(job_id='j')) or 'j'))
            plans.report_start(1, 'p')
        saved = next(call.kwargs['c'] for call in transaction.val.call_args_list if 'c' in call.kwargs)
        return saved, model.call_args.args[1]

    def test_new_report_saves_course_id_and_sends_official_name_to_model(self):
        for pid in OFFICIAL:
            for stored_name in (OFFICIAL[pid], LEGACY[pid]):
                with self.subTest(pid=pid, stored_name=stored_name):
                    saved, model_input = self._run_report({'opt': pid, 'name': stored_name})
                    self.assertEqual((saved['opt'], saved['version']), (pid, 2))
                    self.assertEqual(model_input['planName'], OFFICIAL[pid])

    def test_old_reports_with_track_names_are_read_as_course_ids(self):
        stored = ['Free Track', 'Fast Track', 'Challenge Track', 'A2', '가상 코스']
        rows = [{'report_id': str(i), 'roadmap_id': 'p', 'report_content': {'gained': [], 'opt': opt, 'version': 2},
                 'created_at': datetime.now(timezone.utc), 'confirmed': True} for i, opt in enumerate(stored)]
        with patch.object(plans.db, 'all_', return_value=rows):
            for for_mgr in (False, True):
                with self.subTest(for_mgr=for_mgr):
                    self.assertEqual([r['opt'] for r in plans.reports(1, for_mgr=for_mgr)], ['A1', 'A2', 'A3', 'A2', '가상 코스'])
        self.assertEqual(rows[1]['report_content']['opt'], 'Fast Track')


if __name__ == '__main__':
    unittest.main()
