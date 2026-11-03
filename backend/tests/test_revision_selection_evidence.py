from contextlib import contextmanager
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch

from app.services import plans, prompt_selection_store as store
from app.services.prompt_selection_metrics import summarize


@contextmanager
def transaction(tx):
    yield tx


class RevisionSelectionEvidenceTests(TestCase):
    def setUp(self):
        generation = {'key': 'generation', 'options': {
            course: {'optionId': course + '-option', 'promptProvenance': {'promptVersionId': course + '-version', 'source': 'ollama'}}
            for course in ('A1', 'A2', 'A3')}}
        visible = [{'course': course, 'optionId': course + '-option', 'promptVersionId': course + '-version'}
                   for course in ('A1', 'A2', 'A3')]
        draft = {'chosen': 'A1', 'gen': generation, 'selectionComparison': store.comparison_snapshot(generation, visible)}
        self.evidence = store.confirmation_evidence('decision', draft)

    def accept(self, baseline, current, target='A2'):
        to = {'opt': target, 'def': {}, 'name': target, 'tagline': 'Revised', 'acts': [],
              'selectionEvidence': {'forged': True}}
        revision = {'to': to, 'label': 'Revision', 'prefsTo': {}, 'handoff': {}}
        row = {'roadmap_id': 'roadmap', 'content': current}
        tx = Mock()
        tx.one.side_effect = [{'status': 'ready', 'result': revision}, {'baseline_content': baseline}]
        original = deepcopy((baseline, current, revision))
        with patch.object(plans, '_owned', return_value=row), \
             patch.object(plans.db, 'tx', side_effect=lambda: transaction(tx)), \
             patch.object(plans, 'validate_free_plan'), \
             patch.object(plans, '_write_steps') as write, \
             patch.object(plans, 'record', return_value={'ok': True}), \
             patch('app.services.drafts.selection_of', return_value={}):
            plans.accept_revision(1, 'roadmap', 'revision')
        self.assertEqual((baseline, current, revision), original)
        self.assertFalse(any('SET baseline_content' in call.args[0] for call in tx.run.call_args_list))
        return write.call_args.args[2]

    def test_course_change_preserves_first_evidence_instead_of_revision_payload(self):
        baseline = {'selectionEvidence': deepcopy(self.evidence)}
        current = {'opt': 'A1', 'version': 1, 'selectionEvidence': {'tampered': True}}
        result = self.accept(baseline, current)
        self.assertEqual(result['selectionEvidence'], self.evidence)
        self.assertIsNot(result['selectionEvidence'], baseline['selectionEvidence'])
        self.assertEqual(result['opt'], 'A2')
        self.assertEqual(summarize([result['selectionEvidence']])['eligibleDecisions'], 1)

    def test_repeat_revision_and_missing_current_evidence_restore_same_baseline(self):
        baseline = {'selectionEvidence': self.evidence}
        first = self.accept(baseline, {'opt': 'A1', 'version': 1}, 'A2')
        second = self.accept(baseline, first, 'A3')
        self.assertEqual(second['selectionEvidence'], self.evidence)
        self.assertEqual(second['version'], 3)
        self.assertEqual(summarize([first['selectionEvidence'], second['selectionEvidence']])['eligibleDecisions'], 1)

    def test_legacy_current_evidence_preserved_but_not_backfilled_to_baseline(self):
        current = {'opt': 'A1', 'version': 1, 'selectionEvidence': self.evidence}
        result = self.accept({}, current)
        self.assertEqual(result['selectionEvidence'], self.evidence)

    def test_missing_evidence_is_not_invented_from_revision(self):
        result = self.accept({}, {'opt': 'A1', 'version': 1})
        self.assertNotIn('selectionEvidence', result)

    def test_reader_does_not_issue_writes_or_count_current_content(self):
        with patch.object(store.db, 'all_', return_value=[{'evidence': self.evidence}]) as read:
            result = store.read_decisions()
        self.assertEqual(result, [self.evidence])
        sql = read.call_args.args[0]
        self.assertIn("baseline_content -> 'selectionEvidence'", sql)
        self.assertNotIn('COALESCE', sql.upper())
        self.assertTrue(sql.startswith('SELECT '))
