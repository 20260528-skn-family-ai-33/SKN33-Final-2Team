from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch

from app.agents import roadmap
from app.agents.roadmap_display import MARKER, with_display_contract
from app.agents.roadmap_generation import generation
from app.agents.roadmap_revision import revision
from app.services.duration_proposals import apply_plan_schedule
from tools.migrate_duration_prompts import transform


def example_plan():
    courses = [{'id': 'course', 'hours': 13.5, 'timeStatus': 'confirmed'}]
    rec = {'id': 'rec', 'skills': [{'name': name, 'courses': courses, 'books': [{'id': 'book'}]} for name in ['SQL', 'DB']]}
    return {'hours': 5, 'weeks': 99, 'def': {'materialSchedule': [], 'learningReport': {
        'recommendations': rec, 'choices': {name: {'course': 'course', 'books': ['book']} for name in ['SQL', 'DB']}, 'skillOrder': ['SQL', 'DB']}},
        'acts': [{'id': name + rid, 'skill': name, 'res': rid, 'hours': 10} for name in ['SQL', 'DB'] for rid in ['course', 'book']] +
                [{'id': 'task', 'skill': 'SQL', 'res': None, 'hours': 8}]}


class DurationDisplayTests(TestCase):
    def test_legacy_material_schedule_is_normalized_in_every_roadmap_status(self):
        from app.services import plans

        source = example_plan()
        source['def']['materialSchedule'] = [{'skill': 'SQL', 'weeks': 4}]
        before = deepcopy(source)
        row = dict(roadmap_id='roadmap', content=source, created_at=None, done_at=None,
                   archived_at=None, resumed_at=None)
        with patch.object(plans.db, 'all_', return_value=[]), patch.object(plans, '_comments', return_value=[]), \
             patch.object(plans.catalog, 'refresh_book_links', side_effect=lambda books: books), \
             patch.object(plans.catalog, 'refresh_course_levels', side_effect=lambda courses: courses):
            records = [plans.record(dict(row, status=status), for_mgr=True)
                       for status in ('IN_PROGRESS', 'ARCHIVED', 'COMPLETED', 'IN_PROGRESS')]
        self.assertEqual([record['status'] for record in records], ['active', 'archived', 'done', 'active'])
        normalized = records[0]['plan']
        self.assertNotEqual(normalized['weeks'], before['weeks'])
        for record in records[1:]:
            self.assertEqual(record['plan'], normalized)
        self.assertEqual(source, before)

    def test_other_resources_are_not_tasks_and_shared_ids_count_once(self):
        source = example_plan()
        source['acts'] += [dict(id=name, skill='SQL', res='cert', task=True, hours=10)
                           for name in ('cert1', 'cert2')]
        plan = apply_plan_schedule(source)
        self.assertEqual((plan['materialHours'], plan['taskHours'], plan['otherMaterialHours'], plan['totalH']),
                         (13.5, 8, 10, 31.5))
        self.assertEqual(plan['weeks'], 4)
        self.assertEqual(apply_plan_schedule(plan), plan)

    def test_selected_and_replaced_tasks_match_the_review_contract(self):
        from app.services.activity_selection import compose_skill_selection, selection_option, fingerprint
        source = example_plan()
        report = source['def']['learningReport']
        saved = {'generationId': 'g', 'recommendations': report['recommendations'],
                 'resourceChoices': report['choices'], 'skillOrder': report['skillOrder'],
                 'project': {'goal': 'SQL', 'details': {'hours': 5}}}
        option = dict(source['def'], id='A2', name='Crash', short='', tagline='', acts=source['acts'])
        for act in option['acts']:
            act.update(stage=2 if act.get('res') else 3, title=act['id'], how='')
        draft = {'chosen': 'A2', 'handoff': {'key': 'h', 'prefs': {'weeklyHours': 5}},
                 'gen': {'options': {'A2': option}}}
        record = {'id': 'base', 'key': fingerprint(saved, draft), 'option': option,
                  'selectedIds': [act['id'] for act in option['acts']]}
        other = deepcopy(record)
        other['id'] = 'alternative'
        other['option']['acts'][-1].update(id='replacement', hours=3)
        saved.update(activityProposal=record, activityVersions=[record, other])
        resources = {'course': {'id': 'course', 'type': 'course', 'hours': 13.5, 'cost': 1000},
                     'book': {'id': 'book', 'type': 'book', 'hours': 10, 'cost': None}}
        with patch.object(roadmap, '_res', side_effect=resources.get):
            for task in (True, False):
                selected = [act['id'] for act in option['acts'] if task or act.get('res')]
                chosen = selection_option(saved, draft, selected, 'base')
                plan = roadmap.build_plan(chosen, {'hours': 5}, 'SQL')
                self.assertEqual((plan['weeks'], plan['materialHours'], plan['taskHours']), (4, 13.5, 8 if task else 0))
                self.assertEqual(next(act for act in plan['acts'] if act.get('res') == 'book')['hours'], 10)
            composed = compose_skill_selection(saved, draft, 'base', {'SQL': 'alternative'})
            saved['activityVersions'].append(composed)
            selected = [act['id'] for act in composed['option']['acts']]
            plan = roadmap.build_plan(selection_option(saved, draft, selected, composed['id']), {'hours': 5}, 'SQL')
            self.assertEqual((plan['taskHours'], plan['totalH']), (3, 16.5))

    def test_material_allocation_task_separation_and_catalog_preservation(self):
        source = example_plan()
        before = deepcopy(source)
        plan = apply_plan_schedule(source)
        self.assertEqual((plan['weeks'], plan['materialHours'], plan['taskHours'], plan['totalH']), (4, 13.5, 8, 21.5))
        books = [a for a in plan['acts'] if a['res'] == 'book']
        self.assertTrue(all(a['hours'] == 10 and 'resourceWindow' not in a and 'hoursAllocation' not in a for a in books))
        self.assertEqual(source, before)
        self.assertEqual(apply_plan_schedule(plan), plan)
        plan['hours'] = 10
        revised = apply_plan_schedule(plan)
        self.assertEqual((revised['weeks'], revised['materialHours'], revised['taskHours']), (3, 13.5, 8))
        self.assertTrue(all(a['hours'] == 10 for a in revised['acts'] if a['res'] == 'book'))
        self.assertEqual(plan['acts'][1]['hours'], 10)

    def test_unknown_time_remains_unknown_but_has_explicit_one_week_allocation(self):
        source = example_plan()
        for row in source['def']['learningReport']['recommendations']['skills']:
            row['courses'][0].update(hours=None, timeStatus='unknown')
        plan = apply_plan_schedule(source)
        self.assertEqual((plan['weeks'], plan['materialHours'], plan['totalH']), (2, 5, 13))
        self.assertTrue(plan['totalHUnknown'])
        self.assertTrue(all(a['hours'] == 5 and a['timeStatus'] == 'unknown' and '미확인' in a['hoursBasis'] for a in plan['acts'] if a['res'] == 'course'))

    def test_old_confirmed_plan_is_not_recalculated(self):
        source = example_plan()
        del source['def']['learningReport']
        before = deepcopy(source)
        self.assertIs(apply_plan_schedule(source), source)
        self.assertEqual(source, before)

    def test_team_step_json_keeps_allocation_and_catalog_reference(self):
        from app.services.plans import _write_steps
        plan = apply_plan_schedule(example_plan())
        plan['opt'] = 'A2'
        for activity in plan['acts']:
            activity.update(stage=2, title=activity['id'], how='검증', task=not activity['res'])
        tx = Mock()
        tx.all.return_value = []
        tx.val.return_value = 1
        with patch('app.services.plans.catalog.items', return_value={}):
            _write_steps(tx, '00000000-0000-0000-0000-000000000001', plan)
        details = [call.kwargs['d'].obj for call in tx.val.call_args_list]
        books = [row for row in details if row['res'] == 'book']
        self.assertEqual(len(books), 2)
        self.assertTrue(all(row['hours'] == 10 and row['hoursAllocation'] is None for row in books))

    def test_active_db_and_new_templates_receive_one_contract_each(self):
        import json
        for pid in ('A1', 'A2', 'A3'):
            for text in (generation(pid), revision(pid)):
                self.assertEqual(text.count(MARKER), 1)
                self.assertEqual(with_display_contract(text), text)
                json.loads(text.split('JSON 형식 예: ', 1)[1])
            full = '### GENERATION\n기존 생성 지침\n### REVISION\n기존 수정 지침'
            changed = transform(full)
            self.assertEqual(changed.count(MARKER), 2)
            self.assertEqual(transform(changed), changed)
            with patch.object(roadmap.db, 'all_', return_value=[{'system_prompt': full}]):
                for selector in (roadmap.R_SYS, roadmap.REV_SYS):
                    self.assertEqual(roadmap._sys(pid, selector).count(MARKER), 1)

    def test_malformed_prompt_never_silently_replaces_existing_policy(self):
        for text in ('legacy', '### GENERATION\n\n### REVISION\nx'):
            with self.assertRaises(ValueError):
                transform(text)
