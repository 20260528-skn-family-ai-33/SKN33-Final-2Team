import copy
import unittest
from unittest.mock import patch

from app import catalog, catalog_budget as budget
from app.agents import roadmap
from tests.test_catalog_candidates import resources, measured


class ModelSkillHandoffTests(unittest.TestCase):
    def handoff(self, count):
        names = [f'skill-{i}' for i in range(count)]
        return {'goal': 'SQL 분석', 'prefs': {}, 'selectedSkillsFixed': True,
                'skillOrder': names, 'skillDetails': [{'name': name, 'application': 'SQL 검증'} for name in names],
                'focus': list(names), 'skillNames': list(names), 'domain': ' · '.join(names),
                'assessment': {'groups': [], 'answers': {}}, 'key': 'stored-key'}

    def test_all_tracks_keep_one_to_three_fixed_skills_without_duplicate_model_fields(self):
        for count in range(1, 4):
            for course in ('A1', 'A2', 'A3'):
                with self.subTest(count=count, course=course):
                    h = self.handoff(count)
                    before = copy.deepcopy(h)
                    with patch.object(catalog, 'items', return_value=resources(count, 2)), patch.object(budget, 'tokens', side_effect=measured):
                        result = roadmap._catalog_payload(course, {'handoff': h})
                    sent = result['handoff']
                    self.assertTrue({'focus', 'skillNames', 'domain'}.isdisjoint(sent))
                    self.assertEqual(sent['skillOrder'], before['skillOrder'])
                    self.assertEqual(sent['skillDetails'], before['skillDetails'])
                    self.assertEqual(sent['assessment'], before['assessment'])
                    self.assertEqual(list(result['catalogSkillMap'].values()), before['skillOrder'])
                    self.assertEqual(h, before)

    def test_search_uses_fixed_order_instead_of_obsolete_duplicate_lists(self):
        h = self.handoff(3)
        h['focus'] = h['skillNames'] = ['old-skill']
        with patch.object(catalog, 'items', return_value=resources(3, 1)), patch.object(budget, 'tokens', side_effect=measured):
            result = roadmap._catalog_payload('A2', {'handoff': h})
        self.assertEqual(list(result['catalogSkillMap'].values()), h['skillOrder'])
        self.assertEqual({row['id'] for row in result['catalog']}, {f'{i}-00' for i in range(3)})

    def test_saved_four_and_five_fixed_skills_send_first_three_on_every_track(self):
        for count in (4, 5):
            for course in ('A1', 'A2', 'A3'):
                with self.subTest(count=count, course=course):
                    h = self.handoff(count)
                    before = copy.deepcopy(h)
                    with patch.object(catalog, 'items', return_value=resources(count, 2)), patch.object(budget, 'tokens', side_effect=measured):
                        result = roadmap._catalog_payload(course, {'handoff': h})
                    self.assertEqual(result['handoff']['skillOrder'], before['skillOrder'][:3])
                    self.assertEqual(list(result['catalogSkillMap'].values()), before['skillOrder'][:3])
                    self.assertEqual([row['name'] for row in result['handoff']['skillDetails']], before['skillOrder'][:3])
                    self.assertEqual(h, before)

    def test_duplicates_are_removed_before_token_budget_is_measured(self):
        h = self.handoff(2)
        def capture(selection, system, payload, context_limit):
            self.assertTrue({'focus', 'skillNames', 'domain'}.isdisjoint(payload['handoff']))
            return payload
        with patch.object(catalog, 'items', return_value=resources(2, 1)), patch.object(budget, 'pack', side_effect=capture):
            roadmap._catalog_payload('A3', {'handoff': h}, context_limit=16384)
        self.assertIn('focus', h)

    def test_legacy_handoff_without_fixed_order_keeps_its_contract(self):
        h = self.handoff(2)
        h.pop('selectedSkillsFixed')
        h.pop('skillOrder')
        with patch.object(catalog, 'items', return_value=resources(2, 1)), patch.object(budget, 'tokens', side_effect=measured):
            result = roadmap._catalog_payload('A3', {'handoff': h})
        for field in ('focus', 'skillNames', 'domain'):
            self.assertEqual(result['handoff'][field], h[field])

    def test_assessment_projection_happens_before_budget_without_changing_original(self):
        from tests.test_assessment_context import AssessmentContextTests
        h=self.handoff(2);h['assessment']=AssessmentContextTests().sample();h['assessment']['groups'][0]['skill']=h['skillOrder'][0]
        before=copy.deepcopy(h)
        def capture(selection,system,payload,context_limit):
            self.assertEqual(payload['handoff']['assessment']['version'],'assessment-evidence/v1')
            self.assertEqual(payload['handoff']['assessment']['skills'][0]['quizzes'][0]['result'],'incorrect')
            return payload
        with patch.object(catalog,'items',return_value=resources(2,1)),patch.object(budget,'pack',side_effect=capture):
            roadmap._catalog_payload('A1',{'handoff':h})
        self.assertEqual(h,before)
