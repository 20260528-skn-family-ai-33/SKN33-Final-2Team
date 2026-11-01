from pathlib import Path
from unittest import TestCase
from app.services.prompt_evaluation_replay import load_cases


class FixedPromptCasesTests(TestCase):
    def test_pack_has_four_unique_cases_and_both_generation_and_revision_inputs(self):
        path = Path(__file__).resolve().parents[1] / 'evals' / 'prompt_cases.v1.json'
        cases = load_cases(str(path))
        self.assertEqual(len(cases), 4)
        self.assertEqual(len({row['caseId'] for row in cases}), 4)
        self.assertEqual({row['caseSetId'] for row in cases}, {'growpath-synthetic-projects-v1'})
        for row in cases:
            with self.subTest(case=row['caseId']):
                self.assertGreaterEqual(len(row['rubric']), 3)
                self.assertTrue(row['revision']['request'])
                self.assertEqual(row['handoff']['prefs']['deadlineWeeks'], 6)
                self.assertEqual(row['handoff']['skillNames'], row['handoff']['focus'])
                self.assertTrue(row['handoff']['courseSkillSelection'])
                self.assertNotIn('profile', row['handoff'])
                self.assertNotIn('projectFile', row['handoff'])

    def test_known_technology_and_owned_qualification_cases_remain_distinct(self):
        cases = load_cases(str(Path(__file__).resolve().parents[1] / 'evals' / 'prompt_cases.v1.json'))
        by_id = {row['caseId']: row for row in cases}
        sql = by_id['sql-join-validation']['handoff']
        async_case = by_id['python-async-failure-handling']['handoff']
        self.assertEqual(sql['learnerKnowledge']['certifications'], ['SQLD'])
        self.assertEqual(async_case['learnerKnowledge']['technologies'], ['Python'])
        self.assertIn('실패 처리', async_case['skillDetails'][0]['application'])
