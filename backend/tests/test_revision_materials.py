from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from app import llm
from app.agents import roadmap
from app.services.material_plan import rebuild_revision


class RevisionMaterialsTests(TestCase):
    def setUp(self):
        self.resources = {
            'c1': {'id': 'c1', 'title': 'Course', 'type': 'course', 'hours': 8, 'skills': ['SQL'], 'cost': 0},
            'c2': {'id': 'c2', 'title': 'Added', 'type': 'course', 'hours': 12, 'skills': ['SQL'], 'cost': 0},
            'b1': {'id': 'b1', 'title': 'Book', 'type': 'book', 'hours': 100, 'skills': ['SQL'], 'cost': 1000}}
        self.old = {'opt': 'A1', 'hours': 4, 'start': 2, 'acts': [
            {'id': 'old-course', 'skill': 'SQL', 'stage': 2, 'title': 'Course', 'res': 'c1', 'hours': 8, 'how': ''},
            {'id': 'old-task', 'skill': 'SQL', 'stage': 3, 'title': 'Task', 'res': None, 'hours': 40, 'how': ''}],
            'def': {'learningSkills': [{'name': 'SQL', 'application': 'Practice'}], 'learningReport': {
                'skillOrder': ['SQL'], 'choices': {'SQL': {'course': 'c1', 'books': []}},
                'skillDetails': [{'name': 'SQL', 'application': 'Practice', 'competencySummary': ['Old outcome']}]}}}
        self.handoff = {'startStage': 2, 'prefs': {'weeklyHours': 4}}
        self.option = {'id': 'A1', 'name': 'Free', 'short': 'Free', 'tagline': '',
                       'acts': [dict(a, key=a['id']) for a in deepcopy(self.old['acts'])]}
        self.lookup = patch.object(roadmap, '_res', side_effect=lambda rid: self.resources.get(rid))
        self.lookup.start(); self.addCleanup(self.lookup.stop)

    def rebuild(self):
        return rebuild_revision(self.option, self.old, self.handoff)

    def test_cannot_select_new_version_for_skill_with_completed_activity(self):
        from app.services import plans
        current = {
            'opt': 'free',
            'def': {'learningReport': {'skillOrder': ['SQL']}},
            'acts': [{'id': 'done', 'skill': 'SQL'}, {'id': 'pending', 'skill': 'SQL'}],
        }
        proposal = dict(current, acts=[current['acts'][0], {'id': 'replacement', 'skill': 'SQL'}])
        with self.assertRaises(plans.ApiError) as ctx:
            plans._mix_revision_skills(current, proposal, {}, ['SQL'], {'done'})
        self.assertEqual(ctx.exception.code, 'REVISION_CHANGED')

    def test_retained_id_and_skill_come_from_existing_activity_not_model(self):
        self.option['acts'][0]['skill'] = 'Invented'
        out = self.rebuild()
        out = roadmap.keep_ids(out, self.old, 2)
        self.assertEqual(out['acts'][0]['id'], 'old-course')
        self.assertEqual(out['acts'][0]['skill'], 'SQL')
        self.assertEqual(out['learningReport']['skillDetails'][0]['competencySummary'], ['Old outcome'])

    def test_added_course_and_book_rebuild_details_clear_changed_summary(self):
        for rid in ('c2', 'b1'):
            self.option['acts'].append({'id': rid, 'stage': 2, 'title': rid, 'res': rid, 'hours': 1, 'how': ''})
        out = self.rebuild(); report = out['learningReport']
        self.assertEqual(report['choices']['SQL']['courses'], ['c1', 'c2'])
        self.assertEqual(report['choices']['SQL']['books'], ['b1'])
        self.assertEqual(report['durationEstimates']['SQL']['weeks'], 5)
        self.assertEqual(report['skillDetails'][0]['competencySummary'], [])
        plan = roadmap.build_plan(out, {'hours': 4, 'start': 2}, 'Goal')
        self.assertEqual(plan['weeks'], 5)  # 2 + 3 course weeks

    def test_changed_weekly_time_recalculates_without_task_time(self):
        self.handoff['prefs']['weeklyHours'] = 8
        out = self.rebuild()
        self.assertEqual(out['materialSchedule'], [{'skill': 'SQL', 'weeks': 1, 'startWeek': 1,
                                                   'endWeek': 1, 'addedWeeks': 1, 'totalWeeks': 1}])

    def test_unknown_skill_fails_without_mutating_existing_plan(self):
        original = deepcopy(self.old)
        self.option['acts'].append({'id': 'x', 'stage': 3, 'res': None, 'title': 'Unknown', 'hours': 4})
        with self.assertRaises(llm.LlmError): self.rebuild()
        self.assertEqual(self.old, original)

    def test_ambiguous_resource_skill_fails(self):
        self.old['def']['learningReport']['skillOrder'].append('Python')
        self.resources['c2']['skills'] = ['SQL', 'Python']
        self.option['acts'].append({'id': 'x', 'stage': 2, 'title': 'Added', 'res': 'c2'})
        with self.assertRaises(llm.LlmError): self.rebuild()

    def test_replacement_does_not_reuse_completion_id(self):
        self.option['acts'][0].update(res='c2', key='old-course')
        out = roadmap.keep_ids(self.rebuild(), self.old, 2)
        self.assertNotEqual(out['acts'][0]['id'], 'old-course')

    def test_removed_material_clears_summary_and_no_fake_duration(self):
        self.option['acts'] = self.option['acts'][1:]
        out = self.rebuild()
        self.assertEqual(out['materialSchedule'][0]['weeks'], 0)
        self.assertEqual(out['learningReport']['recommendations']['skills'][0]['courses'], [])
        self.assertEqual(out['learningReport']['skillDetails'][0]['competencySummary'], [])

    def test_legacy_plan_keeps_total_activity_duration(self):
        self.old['def'] = {}
        out = self.rebuild()
        self.assertNotIn('materialSchedule', out)
        self.assertEqual(roadmap.build_plan(out, {'hours': 4, 'start': 2}, 'Goal')['weeks'], 12)

    def test_same_resource_in_two_skills_keeps_separate_ids(self):
        self.old['acts'].append(dict(self.old['acts'][0], id='other-course', skill='Python'))
        self.old['def']['learningReport']['skillOrder'].append('Python')
        self.option['acts'].append(dict(self.old['acts'][-1], key='other-course'))
        out = roadmap.keep_ids(self.rebuild(), self.old, 2)
        self.assertEqual([a['id'] for a in out['acts']], ['old-course', 'old-task', 'other-course'])

    def test_all_course_revisions_keep_actual_duration_over_input_period(self):
        self.handoff['prefs']['deadlineWeeks']=1
        for course in ('A1','A2','A3'):
            self.option['id']=course
            out=self.rebuild()
            self.assertEqual(out['materialSchedule'][0]['weeks'],2)

    def test_revision_llm_error_converts_to_api_error_without_name_error(self):
        from app.services import plans
        from app.errors import ApiError

        # 1) _skill_comment_option 에서 LlmError 발생 시 SKILL_REVISION_INVALID 422 반환
        with patch('app.services.material_plan.rebuild_revision', side_effect=llm.LlmError('스킬 소속 불명확')):
            out = {'acts': [
                {'skill': 'SQL', 'res': 'c2', 'title': 'Added', 'how': ''},
                {'skill': 'SQL', 'res': None, 'title': 'New Task', 'how': 'New How'}
            ]}
            targets = {'course': {'id': 'old-course'}, 'task': {'id': 'old-task'}}
            with self.assertRaises(ApiError) as ctx:
                plans._skill_comment_option(out, self.old, targets, 'SQL', self.handoff)
            self.assertEqual(ctx.exception.status, 422)
            self.assertEqual(ctx.exception.code, 'SKILL_REVISION_INVALID')

        # 2) _mix_revision_skills 에서 LlmError 발생 시 REVISION_SKILLS_INVALID 422 반환
        proposal = deepcopy(self.old)
        proposal['acts'] = [
            {'id': 'new-task', 'skill': 'SQL', 'stage': 2, 'title': 'New Task', 'res': None, 'hours': 40, 'how': ''}
        ]
        with patch('app.services.material_plan.rebuild_revision', side_effect=llm.LlmError('자료 오류')):
            with self.assertRaises(ApiError) as ctx:
                plans._mix_revision_skills(self.old, proposal, self.handoff, ['SQL'], set())
            self.assertEqual(ctx.exception.status, 422)
            self.assertEqual(ctx.exception.code, 'REVISION_SKILLS_INVALID')

    def test_revise_start_rejects_stale_version_before_and_during_registration(self):
        from contextlib import nullcontext
        from unittest.mock import Mock
        from app.services import plans

        base = deepcopy(self.old)
        base.update(version=2, prefs={}, handoff={'startStage': 2, 'prefs': {}})
        row = {'roadmap_id': 'rid', 'project_id': 'pid', 'status': 'IN_PROGRESS', 'content': base}
        body = {'version': 1, 'rev': {'on': {'hours': True}, 'v': {'hours': 6}, 'note': '시간 조정'}}

        with patch.object(plans, '_owned', return_value=row), \
             patch.object(plans.jobs, 'start') as start_job:
            with self.assertRaises(plans.ApiError) as err:
                plans.revise_start(1, 'rid', body)
            self.assertEqual((err.exception.status, err.exception.code), (409, 'REVISION_CHANGED'))
            start_job.assert_not_called()

        tx = Mock()
        tx.val.side_effect = ['IN_PROGRESS', None]
        tx.one.return_value = {'content': dict(base, version=3)}
        body_same_version = {'version': 2, 'rev': {'on': {'hours': True}, 'v': {'hours': 6}, 'note': '시간 조정'}}
        with patch.object(plans, '_owned', return_value=row), \
             patch.object(plans.db, 'all_', return_value=[]), \
             patch.object(plans.db, 'tx', side_effect=lambda: nullcontext(tx)), \
             patch.object(plans.jobs, 'start') as start_job:
            with self.assertRaises(plans.ApiError) as err:
                plans.revise_start(1, 'rid', body_same_version)
            self.assertEqual((err.exception.status, err.exception.code), (409, 'REVISION_CHANGED'))
            start_job.assert_not_called()

    def test_multi_course_skill_comment_replaces_undone_course_while_keeping_completed_course(self):
        from contextlib import nullcontext
        from unittest.mock import Mock
        from app.services import plans

        base = {
            'opt': 'A2', 'goal': 'SQL 목표', 'hours': 4, 'start': 2, 'version': 1, 'prefs': {}, 'handoff': {'startStage': 2, 'prefs': {}},
            'acts': [
                {'id': 'done-course', 'skill': 'SQL', 'stage': 2, 'title': 'Course', 'res': 'c1', 'hours': 8, 'how': ''},
                {'id': 'undone-course', 'skill': 'SQL', 'stage': 2, 'title': 'Added', 'res': 'c2', 'hours': 12, 'how': ''},
                {'id': 'undone-task', 'skill': 'SQL', 'stage': 3, 'title': 'Task', 'res': None, 'hours': 4, 'how': ''},
            ],
            'def': deepcopy(self.old['def']),
        }
        row = {'roadmap_id': 'rid', 'project_id': 'pid', 'status': 'IN_PROGRESS', 'content': base}
        comments = [{'id': 'c-1', 'skill': 'SQL', 'fit': 'partial', 'fitText': '강좌·도서', 'level': 'none', 'levelText': '', 'free': '새 강좌', 'deleted': False, 'status': 'new', 'stamp': 's1'}]
        captured = {}

        def fake_start(kind, emp, rid, work, *, before_start=None, transaction=None):
            captured['work'] = work
            return 'job-1'

        tx = Mock()
        tx.val.side_effect = ['IN_PROGRESS', None, 'rev-1']
        tx.one.return_value = {'content': base}

        with patch.object(plans, '_owned', return_value=row), \
             patch.object(plans, '_comments', return_value=comments), \
             patch.object(plans.db, 'all_', side_effect=[[{'activity_id': 'done-course'}]]), \
             patch.object(plans.db, 'tx', side_effect=lambda: nullcontext(tx)), \
             patch.object(plans.jobs, 'start', side_effect=fake_start), \
             patch.object(plans.RM, '_res', side_effect=lambda rid: self.resources.get(rid)):
            res = plans.revise_start(1, 'rid', {'rev': {'fromComment': 'c-1', 'on': {}, 'v': {}, 'note': '보완'}})
        self.assertEqual(res['revisionId'], 'rev-1')

        # 2개 강좌 모두 완료되고 산출물만 미완료면 강좌는 교체 대상에서 제외되고 산출물만 대상이 된다
        tx_all_done = Mock()
        tx_all_done.val.side_effect = ['IN_PROGRESS', None, 'rev-2']
        tx_all_done.one.return_value = {'content': base}
        with patch.object(plans, '_owned', return_value=row), \
             patch.object(plans, '_comments', return_value=comments), \
             patch.object(plans.db, 'all_', side_effect=[[{'activity_id': 'done-course'}, {'activity_id': 'undone-course'}]]), \
             patch.object(plans.db, 'tx', side_effect=lambda: nullcontext(tx_all_done)), \
             patch.object(plans.jobs, 'start', side_effect=fake_start), \
             patch.object(plans.RM, '_res', side_effect=lambda rid: self.resources.get(rid)), \
             patch.object(plans.RM, 'revise', return_value={'acts': [
                 {'skill': 'SQL', 'res': None, 'title': 'Only Task', 'how': '새 과제', 'stage': 3, 'hours': 4},
             ]}), \
             patch.object(plans.RM, 'keep_ids', side_effect=lambda out, old, v: {'acts': [dict(a, id=f'keep-{i}') for i, a in enumerate(out['acts'])], 'weeklyHours': 4}), \
             patch.object(plans.RM, 'build_plan', return_value={'opt': 'A2', 'acts': [], 'hours': 4, 'start': 2, 'weeks': 2, 'cost': 0}), \
             patch.object(plans.rt, 'context', return_value=Mock()), \
             patch.object(plans.rt, 'sim_once', return_value=None), \
             patch('app.services.material_plan.rebuild_revision', side_effect=lambda option, *_: option):
            plans.revise_start(1, 'rid', {'rev': {'fromComment': 'c-1', 'on': {}, 'v': {}, 'note': '보완'}})
            captured['work'](Mock())
        self.assertEqual(tx_all_done.run.call_args.kwargs['p'].obj['skillComment']['targets'], ['undone-task'])

        # 1개 완료 + 1개 미완료인 호출: done-course 는 제외, undone-course 와 undone-task 가 교체 대상
        seen_inp = {}
        tx_exec = Mock()
        tx_exec.val.side_effect = ['IN_PROGRESS', None, 'rev-3']
        tx_exec.one.return_value = {'content': base}
        with patch.object(plans, '_owned', return_value=row), \
             patch.object(plans, '_comments', return_value=comments), \
             patch.object(plans.db, 'all_', side_effect=[[{'activity_id': 'done-course'}]]), \
             patch.object(plans.db, 'tx', side_effect=lambda: nullcontext(tx_exec)), \
             patch.object(plans.jobs, 'start', side_effect=fake_start), \
             patch.object(plans.RM, '_res', side_effect=lambda rid: self.resources.get(rid)), \
             patch.object(plans.RM, 'revise', side_effect=lambda ctx, inp, **kw: (seen_inp.update(inp), {'acts': [
                 {'skill': 'SQL', 'res': 'c3', 'title': 'Replaced', 'how': '', 'stage': 2, 'hours': 4},
                 {'skill': 'SQL', 'res': None, 'title': 'New Task', 'how': '새 과제', 'stage': 3, 'hours': 4},
             ]})[1]), \
             patch.object(plans.RM, 'keep_ids', side_effect=lambda out, old, v: {'acts': [dict(a, id=f'keep-{i}') for i, a in enumerate(out['acts'])], 'weeklyHours': 4}), \
             patch.object(plans.RM, 'build_plan', return_value={'opt': 'A2', 'acts': [], 'hours': 4, 'start': 2, 'weeks': 2, 'cost': 0}), \
             patch.object(plans.rt, 'context', return_value=Mock()), \
             patch.object(plans.rt, 'sim_once', return_value=None), \
             patch('app.services.material_plan.rebuild_revision', side_effect=lambda option, *_: option):
            self.resources['c3'] = {'id': 'c3', 'title': 'Replaced', 'type': 'course', 'hours': 4, 'skills': ['SQL'], 'cost': 0}
            plans.revise_start(1, 'rid', {'rev': {'fromComment': 'c-1', 'on': {}, 'v': {}, 'note': '보완'}})
            captured['work'](Mock())
        replace_keys = [row['key'] for row in seen_inp['changes']['replaceActs']]
        self.assertEqual(replace_keys, ['undone-course', 'undone-task'])
        self.assertEqual(tx_exec.run.call_args.kwargs['p'].obj['skillComment']['targets'], ['undone-course', 'undone-task'])
