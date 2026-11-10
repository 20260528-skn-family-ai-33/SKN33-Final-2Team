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
