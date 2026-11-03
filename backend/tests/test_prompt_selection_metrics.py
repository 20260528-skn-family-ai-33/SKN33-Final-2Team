from copy import deepcopy
from datetime import datetime, timezone
from unittest import TestCase
from app.services.prompt_selection_metrics import confirmed_decision, summarize


class PromptSelectionMetricsTests(TestCase):
    def event(self, key='project-1', selected='A1'):
        return confirmed_decision(key, datetime(2026, 11, 1, tzinfo=timezone.utc), selected,
            [{'course': course, 'optionId': 'option-' + course, 'promptVersionId': 'version-' + course, 'source': 'ollama'} for course in ('A1', 'A2', 'A3')])

    def test_counts_final_confirmation_once_and_keeps_version_denominators(self):
        first, second = self.event(), self.event('project-2', 'A3')
        second['displayed'][0]['promptVersionId'] = 'new-A1'
        result = summarize([first, deepcopy(first), second])
        self.assertEqual(result['eligibleDecisions'], 2)
        self.assertEqual(result['duplicateEvents'], 1)
        rates = {(row['course'], row['promptVersionId']): row for row in result['rates']}
        self.assertEqual(rates['A1', 'version-A1']['selectionRate'], 1)
        self.assertEqual(rates['A1', 'new-A1']['selectionRate'], 0)
        self.assertEqual(rates['A3', 'version-A3']['selectionRate'], 0.5)

    def test_intermediate_clicks_missing_versions_and_mock_are_not_training_evidence(self):
        click, missing, mock = self.event(), self.event('p2'), self.event('p3')
        click['eventType'] = 'course_clicked'
        missing['displayed'][0]['promptVersionId'] = None
        mock['displayed'][1]['source'] = 'mock'
        result = summarize([click, missing, mock])
        self.assertEqual(result['eligibleDecisions'], 0)
        self.assertEqual(result['skipped'], {'not_finalized': 1, 'missing_provenance': 1, 'non_live_sample': 1})

    def test_partial_generation_is_not_treated_as_a_three_way_comparison(self):
        event = self.event()
        event['displayed'].pop()
        self.assertEqual(summarize([event])['skipped'], {'incomplete_comparison': 1})

    def test_conflicting_duplicate_is_excluded_instead_of_counting_twice(self):
        result = summarize([self.event(), self.event(selected='A3')])
        self.assertEqual(result['eligibleDecisions'], 0)
        self.assertEqual(result['conflictingDecisions'], 1)

    def test_snapshot_drops_personal_text_and_does_not_follow_later_mutation(self):
        shown = self.event()['displayed']
        shown[0]['employeeName'] = '비공개'
        event = confirmed_decision('p', datetime.now(timezone.utc), 'A1', shown)
        shown[0]['promptVersionId'] = 'changed'
        self.assertNotIn('employeeName', event['displayed'][0])
        self.assertEqual(event['displayed'][0]['promptVersionId'], 'version-A1')

    def test_naive_finalization_time_is_rejected(self):
        with self.assertRaises(ValueError):
            confirmed_decision('p', datetime(2026, 11, 1), 'A1', [])
