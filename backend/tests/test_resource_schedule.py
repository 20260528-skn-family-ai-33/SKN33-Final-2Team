"""자료 선택→미리보기→저장→확정 구성→명시적 수정의 기간 계약."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch

from app.agents import roadmap
from app.services import activity_selection, material_plan, survey_store
from app.services.duration_proposals import calculate_durations, resource_schedule, material_duration
from app.agents.resource_recommendations import RecommendationError


class ResourceScheduleTests(TestCase):
    def setUp(self):
        self.resources = {rid: {'id': rid, 'title': rid, 'type': 'course', 'hours': hours, 'cost': 0}
                          for rid, hours in [('shared', 6.9), ('etl', 8.7), ('mlops', 8.7)]}
        self.resources['book'] = {'id': 'book', 'title': 'book', 'type': 'book', 'hours': 12, 'cost': 100}
        self.order = ['RAG', 'Web', 'ETL', 'MLOps']
        ids = ['shared', 'shared', 'etl', 'mlops']
        self.rec = {'id': 'r', 'skills': [{'name': name, 'courses': [deepcopy(self.resources[rid])],
                                        'books': [deepcopy(self.resources['book'])]}
                                       for name, rid in zip(self.order, ids)]}
        self.choices = {name: {'course': rid, 'books': [], 'enabled': True} for name, rid in zip(self.order, ids)}
        self.project = {'goal': 'Goal', 'details': {'hours': 6}}
        self.saved = {'generationId': 'g', 'completed': True, 'project': self.project,
                      'recommendations': self.rec, 'resourceChoices': self.choices, 'skillOrder': self.order}
        self.option = {'id': 'A2', 'name': 'Crash', 'short': 'Crash', 'tagline': '', 'weeklyHours': 6, 'acts': []}
        self.draft = {'chosen': 'A2', 'goal': 'Goal', 'handoff': {'key': 'h', 'startStage': 2, 'prefs': {'weeklyHours': 6}},
                      'gen': {'options': {'A2': self.option}}}
        self.lookup = patch.object(roadmap, '_res', side_effect=self.resources.get)
        self.lookup.start(); self.addCleanup(self.lookup.stop)

    def estimates(self, order=None, weekly=6):
        return calculate_durations({'details': {'hours': weekly}}, self.rec, self.choices, order or self.order, weekly)

    def test_reproduction_is_five_weeks_and_overlapping_windows_are_not_added(self):
        rows = self.estimates()
        self.assertEqual({row['totalWeeks'] for row in rows.values()}, {7})
        self.assertEqual(sum(row['addedWeeks'] for row in rows.values()), 7)
        self.assertGreater(sum(row['weeks'] for row in rows.values()), 7)
        self.assertEqual(rows['RAG']['resources'], rows['Web']['resources'])
        self.assertEqual(rows['Web']['addedWeeks'], 0)
        self.assertEqual((rows['Web']['startWeek'], rows['Web']['endWeek']), (1, 3))

    def test_nonadjacent_sharing_and_book_gap_keep_the_original_course_window(self):
        self.choices['RAG']['books'] = ['book']
        rows = self.estimates(['RAG', 'ETL', 'Web', 'MLOps'])
        self.assertEqual(rows['Web']['addedWeeks'], 0)
        self.assertEqual((rows['Web']['startWeek'], rows['Web']['endWeek']), (1, 3))
        self.assertEqual(rows['Web']['totalWeeks'], 8)
        self.assertEqual(rows['RAG']['bookWeeks'], 1)
        for row in rows.values():
            self.assertLessEqual(row['startWeek'], row['endWeek'])
            self.assertLessEqual(row['endWeek'], row['totalWeeks'])

    def test_distinct_subweek_courses_round_once_and_exact_decimal_boundary(self):
        courses = [{'id': str(i), 'hours': 0.1} for i in range(3)]
        result = material_duration(courses, [], 0.3)
        self.assertEqual(result['totalWeeks'], 3)
        self.assertEqual(result['courseWeeks'], 3)

    def test_shared_book_is_one_week_even_for_nonadjacent_skills(self):
        for name in ('RAG', 'Web'):
            self.choices[name]['books'] = ['book']
        rows = self.estimates(['RAG', 'ETL', 'Web', 'MLOps'])
        self.assertEqual(rows['RAG']['totalWeeks'], 9)
        self.assertEqual(rows['RAG']['bookWeeks'], 1)
        self.assertEqual(rows['Web']['bookWeeks'], 1)
        self.assertEqual(rows['Web']['addedWeeks'], 1)
        self.assertEqual(sum(row['addedWeeks'] for row in rows.values()), 9)
        before = deepcopy(self.saved)
        preview = material_plan.preview(self.saved, self.draft)
        self.assertEqual(preview['weeks'], 9)
        self.assertEqual(preview['totalH'], 30.3)
        books = [a for a in preview['acts'] if a.get('res') == 'book']
        self.assertEqual(len(books), 2)
        self.assertEqual([a['resourceWindow'] for a in books], [{'from': 4, 'to': 4}, {'from': 5, 'to': 5}])
        self.assertEqual(self.saved, before)
        revision = dict(deepcopy(preview['def']), acts=[dict(a, key=a['id']) for a in preview['acts']])
        rebuilt = material_plan.rebuild_revision(revision, preview, self.draft['handoff'])
        revised = roadmap.build_plan(rebuilt, {'hours': 6, 'start': 2}, 'Goal')
        self.assertEqual(revised['weeks'], 9)
        self.assertEqual(revised['totalH'], 30.3)

    def test_book_only_shared_selection_reorder_disable_and_reselect(self):
        for row in self.rec['skills']:
            row['courses'] = []
            self.choices[row['name']]['course'] = None
        self.choices['RAG']['books'] = ['book']
        self.choices['Web']['books'] = ['book']
        rows = self.estimates()
        self.assertEqual(rows['RAG']['totalWeeks'], 2)
        self.assertEqual(rows['Web']['bookWeeks'], 1)
        reordered = self.estimates(list(reversed(self.order)))
        self.assertEqual(reordered['Web']['bookWeeks'], 1)
        self.assertEqual(reordered['RAG']['bookWeeks'], 1)
        self.choices['RAG']['enabled'] = False
        self.assertEqual(self.estimates()['Web']['bookWeeks'], 1)
        self.choices['Web']['books'] = []
        self.assertEqual(self.estimates()['Web']['totalWeeks'], 0)
        self.choices['Web']['books'] = ['book']
        self.assertEqual(self.estimates(weekly=12)['Web']['totalWeeks'], 1)
        self.assertEqual(self.estimates(weekly=12)['Web']['resources'], [{'id': 'book', 'startWeek': 1, 'endWeek': 1}])

    def test_different_book_ids_are_not_deduplicated_by_title(self):
        for row in self.rec['skills']:
            row['courses'] = []
            self.choices[row['name']]['course'] = None
        self.rec['skills'][1]['books'].append(dict(self.resources['book'], id='other-book'))
        self.choices['RAG']['books'] = ['book']
        self.choices['Web']['books'] = ['other-book']
        self.assertEqual(self.estimates()['Web']['totalWeeks'], 2)

    def test_previous_book_schedule_version_cannot_be_saved_as_current(self):
        tx = Mock(); tx.one.return_value = {'draft_choices': {'v2Survey': self.saved, 'draft': self.draft}}
        old = self.estimates()
        for row in old.values(): row['method'] = 'resource-hours-books/v2'
        with self.assertRaises(survey_store.StoreError):
            survey_store.save_duration_proposals(tx, 1, 'p', 'g', 'r', old)
        tx.run.assert_not_called()

    def test_reorder_disable_and_weekly_changes_invalidate_every_row(self):
        original = self.estimates()
        reorder = self.estimates(['ETL', 'Web', 'MLOps', 'RAG'])
        self.assertTrue(all(original[name]['scheduleKey'] != reorder[name]['scheduleKey'] for name in original))
        self.assertEqual(reorder['RAG']['addedWeeks'], 0)
        self.choices['RAG']['enabled'] = False
        disabled = self.estimates()
        self.assertNotIn('RAG', disabled)
        self.assertEqual(disabled['Web']['addedWeeks'], 2)
        self.assertNotEqual(original['ETL']['scheduleKey'], disabled['ETL']['scheduleKey'])
        changed = self.estimates(weekly=12)
        self.assertEqual(changed['Web']['totalWeeks'], 3)
        self.assertNotEqual(disabled['ETL']['scheduleKey'], changed['ETL']['scheduleKey'])

    def test_unknown_and_estimated_are_deterministic_and_not_confirmed(self):
        for row in self.rec['skills']:
            if row['courses'][0]['id'] == 'shared':
                row['courses'][0].update(hours=None, timeStatus='unknown')
            else:
                row['courses'][0]['estimated'] = ['hours']
        rows = self.estimates()
        self.assertEqual(rows['RAG']['unknownCourses'], ['shared'])
        self.assertIsNone(rows['RAG']['resources'][0]['hours'])
        self.assertEqual(rows['ETL']['estimatedCourses'], ['etl'])
        self.assertIn('미확인', rows['RAG']['basis'])
        self.assertEqual(rows['RAG']['totalWeeks'], 6)
        self.assertEqual(rows, self.estimates())

    def test_preview_save_confirm_revision_agree_and_keep_input_and_activity_ids(self):
        before = deepcopy(self.saved)
        expected = self.estimates()
        self.saved['durationEstimates'] = {'RAG': {'weeks': 100, 'method': 'stale'}}
        preview = material_plan.preview(self.saved, self.draft)
        self.assertEqual(preview['weeks'], 7)
        self.assertEqual(preview['totalH'], 24.3)
        self.assertEqual(self.option['acts'], [])
        self.assertEqual(self.saved['recommendations'], before['recommendations'])
        tx = Mock(); tx.one.return_value = {'draft_choices': {'v2Survey': self.saved, 'draft': self.draft}}; tx.run.return_value = 1
        saved = survey_store.save_resource_choices(tx, 1, 'p', 'g', 'r', self.choices, skill_order=self.order)
        self.assertEqual(saved['durationEstimates'], expected)
        acts = [dict(a) for a in preview['acts']]
        acts += [{'id': 'task', 'skill': 'Web', 'stage': 3, 'title': 'Task', 'res': None, 'hours': 100, 'how': 'verify'}]
        record = {'id': 'proposal', 'key': activity_selection.fingerprint(saved, self.draft),
                  'option': dict(self.option, acts=acts), 'selectedIds': [a['id'] for a in acts], 'skillSummaries': {}}
        saved['activityProposal'] = record
        option = activity_selection.selection_option(saved, self.draft, record['selectedIds'])
        original = deepcopy(option)
        confirmed = roadmap.build_plan(option, {'hours': 6, 'start': 2}, 'Goal')
        self.assertEqual(option, original)
        self.assertEqual(confirmed['weeks'], 7)
        self.assertEqual(confirmed['totalH'], 124.3)
        self.assertEqual(confirmed['durationBasis'], 'materials-only')
        self.assertEqual([a['id'] for a in confirmed['acts']], record['selectedIds'])
        shared = [a for a in confirmed['acts'] if a.get('res') == 'shared']
        self.assertEqual([(a['wFrom'], a['wTo']) for a in shared], [(1, 3), (1, 3)])
        source = deepcopy(confirmed)
        revision = dict(deepcopy(option), acts=[dict(a, key=a['id']) for a in confirmed['acts']])
        rebuilt = material_plan.rebuild_revision(revision, confirmed, self.draft['handoff'])
        revised = roadmap.build_plan(rebuilt, {'hours': 6, 'start': 2}, 'Goal')
        self.assertEqual(revised['weeks'], 7)
        self.assertEqual(revised['totalH'], 124.3)
        self.assertEqual(confirmed, source)

    def test_empty_materials_and_all_disabled_do_not_allocate_future_slots(self):
        for row in self.rec['skills']:
            row['courses'] = []
            self.choices[row['name']]['course'] = None
        preview = material_plan.preview(self.saved, self.draft)
        self.assertEqual(preview['weeks'], 0)
        self.assertEqual(preview['totalH'], 0)
        self.assertTrue(all(row['startWeek'] is None and row['endWeek'] is None for row in preview['def']['learningReport']['durationEstimates'].values()))
        for choice in self.choices.values(): choice['enabled'] = False
        self.assertEqual(material_plan.preview(self.saved, self.draft)['weeks'], 0)

    def test_multi_course_revision_rounds_all_unique_hours_once(self):
        rec = {'skills': [{'name': 'S', 'courses': [{'id': str(i), 'hours': 2} for i in range(3)], 'books': []}]}
        choices = {'S': {'course': '0', 'courses': ['0', '1', '2'], 'books': []}}
        self.assertEqual(resource_schedule(rec, choices, ['S'], 6)['weeks'], 3)

    def test_changed_weekly_invalidates_activity_even_without_handoff_key_change(self):
        self.saved['activityProposal'] = {'key': activity_selection.fingerprint(self.saved, self.draft)}
        self.draft['handoff']['prefs']['weeklyHours'] = 12
        self.assertIsNone(activity_selection.current_record(self.saved, self.draft))

    def test_stale_partial_cache_is_rejected_and_current_snapshot_replaces_it(self):
        tx = Mock(); tx.one.return_value = {'draft_choices': {'v2Survey': self.saved, 'draft': self.draft}}; tx.run.return_value = 1
        original = deepcopy(self.saved)
        with self.assertRaises(survey_store.StoreError):
            survey_store.save_duration_proposals(tx, 1, 'p', 'g', 'r', {'RAG': self.estimates()['RAG']})
        tx.run.assert_not_called()
        self.assertEqual(self.saved, original)
        current = survey_store.save_duration_proposals(tx, 1, 'p', 'g', 'r', self.estimates())
        self.assertEqual(current['durationEstimates'], self.estimates())
        self.draft['handoff']['prefs']['weeklyHours'] = 12
        with self.assertRaises(survey_store.StoreError):
            survey_store.save_duration_proposals(tx, 1, 'p', 'g', 'r', self.estimates())

    def test_public_selection_cannot_smuggle_multiple_courses(self):
        self.choices['RAG']['courses'] = ['shared', 'etl']
        with self.assertRaises(RecommendationError): self.estimates()

    def test_same_id_conflicting_cards_are_order_independent_and_use_confirmed_evidence(self):
        self.rec['skills'][0]['courses'][0].update(hours=60, estimated=['hours'])
        rows = self.estimates()
        reversed_rows = self.estimates(list(reversed(self.order)))
        self.assertEqual(rows['RAG']['totalWeeks'], 7)
        self.assertEqual(reversed_rows['RAG']['totalWeeks'], 7)
        self.assertEqual(rows['RAG']['resources'][0]['hours'], 6.9)

    def test_task_only_plan_and_zero_material_plan_are_explicit_about_duration_basis(self):
        for row in self.rec['skills']:
            row['courses'] = []
            self.choices[row['name']]['course'] = None
        report = material_plan.report(self.saved, {})
        option = dict(self.option, learningReport=report, materialSchedule=[],
                      acts=[{'id': 'task', 'skill': 'Web', 'stage': 3, 'title': 'Task', 'res': None, 'hours': 100}])
        plan = roadmap.build_plan(option, {'hours': 6, 'start': 2}, 'Goal')
        self.assertEqual(plan['weeks'], 0)
        self.assertEqual(plan['totalH'], 100)
        self.assertEqual(plan['durationBasis'], 'materials-only')
        self.assertEqual((plan['acts'][0]['wFrom'], plan['acts'][0]['wTo']), (1, 1))

    def test_five_skills_keep_order_and_book_only_skill_adds_exactly_one_week(self):
        self.order.append('Security')
        self.rec['skills'].append({'name': 'Security', 'courses': [], 'books': [self.resources['book']]})
        self.choices['Security'] = {'course': None, 'books': [], 'enabled': True}
        rows = self.estimates()
        self.assertEqual(list(rows), self.order)
        self.assertEqual(rows['Security']['weeks'], 0)
        self.assertIsNone(rows['Security']['startWeek'])
        self.choices['Security']['books'] = ['book']
        rows = self.estimates()
        self.assertEqual(rows['Security']['addedWeeks'], 1)
        self.assertEqual(rows['Security']['totalWeeks'], 8)
