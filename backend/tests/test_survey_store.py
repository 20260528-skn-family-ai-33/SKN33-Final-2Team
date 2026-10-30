import copy
import json
import unittest
from unittest.mock import Mock

from app.services import survey_store as store
import test_survey_generation as fixtures


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SurveyTests()
        self.fixture.setUp()
        self.tx = Mock()
        self.tx.one.return_value = {'draft_choices': {'gp5': 1, 'draft': {'goal': '보존'}}}
        self.tx.run.return_value = 1

    def generated(self):
        return store.save_generated(self.tx, 1, 'project', self.fixture.project,
                                    self.fixture.selection(2), self.fixture.profile, self.fixture.result(2))

    def prepare(self):
        value = self.generated()
        self.tx.one.return_value = {'draft_choices': {store.KEY: value}}
        self.tx.run.reset_mock()
        return value

    def all_answers(self, value):
        return {q['id']: (1 if kind == 'surveys' else 0)
                for g in value['survey']['groups'] for kind in ('surveys', 'quizzes') for q in g[kind]}

    def test_save_preserves_existing_keys_and_snapshots_only_summary(self):
        value = self.generated()
        self.assertIn('jsonb_set', self.tx.run.call_args.args[0])
        self.assertNotIn('rawText', value['project'])
        self.assertEqual(value['profile'], self.fixture.profile)
        self.assertEqual(self.tx.one.return_value['draft_choices']['draft']['goal'], '보존')
        self.assertIn('FOR UPDATE', self.tx.one.call_args.args[0])
        self.assertEqual(json.loads(self.tx.run.call_args.kwargs['value']), value)

    def test_read_returns_identical_but_independent_snapshot(self):
        value = self.prepare()
        loaded = store.read(self.tx, 1, 'project')
        self.assertEqual(loaded, value)
        loaded['answers']['new'] = 1
        self.assertEqual(value['answers'], {})

    def test_wrong_owner_or_non_draft_cannot_read_or_write(self):
        self.tx.one.return_value = None
        with self.assertRaises(store.StoreError): self.generated()
        with self.assertRaises(store.StoreError): store.read(self.tx, 2, 'project')
        self.tx.run.assert_not_called()
        sql = self.tx.one.call_args.args[0]
        self.assertIn('employee_id = :e', sql)
        self.assertIn("status = 'DRAFTING'", sql)

    def test_existing_survey_is_not_silently_replaced(self):
        self.prepare()
        with self.assertRaises(store.StoreError): self.generated()
        self.tx.run.assert_not_called()

    def test_full_answers_preserve_zero_index_and_complete(self):
        value = self.prepare()
        answers = self.all_answers(value)
        result = store.save_answers(self.tx, 1, 'project', value['generationId'], answers, complete=True)
        self.assertTrue(result['completed'])
        self.assertEqual(result['answers'], answers)
        self.assertIn(0, result['answers'].values())

    def test_quiz_cannot_start_before_all_surveys_are_answered(self):
        value = self.prepare()
        quiz = value['survey']['groups'][0]['quizzes'][0]['id']
        with self.assertRaisesRegex(store.StoreError, '설문을 모두'):
            store.save_answers(self.tx, 1, 'project', value['generationId'], {quiz: 0})
        self.tx.run.assert_not_called()

    def test_partial_answers_save_but_completion_is_blocked(self):
        value = self.prepare()
        first = next(iter(self.all_answers(value)))
        result = store.save_answers(self.tx, 1, 'project', value['generationId'], {first: 2})
        self.assertFalse(result['completed'])
        self.tx.run.reset_mock()
        with self.assertRaisesRegex(store.StoreError, '모든 문항'):
            store.save_answers(self.tx, 1, 'project', value['generationId'], {first: 2}, complete=True)
        self.tx.run.assert_not_called()

    def test_old_generation_unknown_question_and_bad_answer_rejected(self):
        value = self.prepare()
        survey = value['survey']['groups'][0]['surveys'][0]['id']
        quiz = value['survey']['groups'][0]['quizzes'][0]['id']
        for token, answers in [('old', {}), (value['generationId'], {'unknown': 1}),
                               (value['generationId'], {survey: 0}), (value['generationId'], {quiz: 5}),
                               (value['generationId'], {survey: True})]:
            with self.subTest(answers=answers), self.assertRaises(store.StoreError):
                store.save_answers(self.tx, 1, 'project', token, answers)
        self.tx.run.assert_not_called()

    def test_public_view_has_no_correct_answers_explanations_or_profile(self):
        value = self.prepare()
        before = copy.deepcopy(value)
        public = store.public_view(value)
        self.assertNotIn('profile', public)
        for group in public['groups']:
            for quiz in group['quizzes']:
                self.assertNotIn('answer', quiz)
                self.assertNotIn('explain', quiz)
        self.assertEqual(value, before)

    def test_malformed_existing_json_and_failed_update_are_errors(self):
        self.tx.one.return_value = {'draft_choices': []}
        with self.assertRaises(store.StoreError): self.generated()
        self.tx.run.assert_not_called()
        self.tx.one.return_value = {'draft_choices': {}}
        self.tx.run.return_value = 0
        with self.assertRaises(store.StoreError): self.generated()


    def test_replacement_creates_new_generation_and_clears_answers(self):
        old = self.prepare()
        old['answers'] = {'old': 3}; old['completed'] = True
        updated = store.save_generated(self.tx, 1, 'project', self.fixture.project,
                    self.fixture.selection(2), self.fixture.profile, self.fixture.result(2),
                    replace_generation_id=old['generationId'])
        self.assertNotEqual(updated['generationId'], old['generationId'])
        self.assertEqual(updated['answers'], {})
        self.assertFalse(updated['completed'])

    def test_another_generation_cannot_be_replaced_by_stale_request(self):
        self.prepare()
        with self.assertRaises(store.StoreError):
            store.save_generated(self.tx, 1, 'project', self.fixture.project,
                    self.fixture.selection(2), self.fixture.profile, self.fixture.result(2),
                    replace_generation_id='old-generation')
        self.tx.run.assert_not_called()


if __name__ == '__main__':
    unittest.main()