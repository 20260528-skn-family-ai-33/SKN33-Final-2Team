"""Track DB prompt routing and free-only contract; no model/network calls."""
import unittest
from unittest.mock import patch
from app import llm
from app.agents import roadmap as rm


class TrackPromptTests(unittest.TestCase):
    def test_db_generation_and_revision_are_selected(self):
        prompt = '### GENERATION\nDB generation\n### REVISION\nDB revision'
        with patch.object(rm.db, 'all_', return_value=[{'system_prompt': prompt}]) as query:
            self.assertEqual(rm._sys('A1', rm.R_SYS), 'DB generation')
            self.assertEqual(rm._sys('A1', rm.REV_SYS), 'DB revision')
            self.assertEqual(query.call_count, 2)
            self.assertEqual(query.call_args.kwargs['agent'], 'agent_certified')

    def test_missing_duplicate_malformed_and_empty_prompts_fail(self):
        for rows in ([], [{'system_prompt': 'x'}] * 2, [{'system_prompt': 'legacy'}],
                     [{'system_prompt': '### GENERATION\n\n### REVISION\nx'}]):
            with self.subTest(rows=rows), patch.object(rm.db, 'all_', return_value=rows):
                with self.assertRaises(llm.LlmError):
                    rm._sys('A1', rm.R_SYS)

    def test_catalog_filter_is_requested_only_for_free(self):
        for pid in ('A1', 'A2', 'A3'):
            with self.subTest(pid=pid), patch.object(rm, 'agent_catalog', return_value=[]) as get_catalog:
                self.assertEqual(rm._track_catalog(pid, {}), [])
                get_catalog.assert_called_once_with({}, None, free_only=pid == 'A1')

    def test_free_output_rejects_paid_and_unknown(self):
        for cost in (100, None):
            with self.subTest(cost=cost), patch.object(rm, '_res', return_value={'cost': cost}):
                with self.assertRaises(llm.LlmError):
                    rm.finish_option('A1', {'acts': [{'res': 'resource'}]}, 'api')

    def test_free_output_accepts_free_and_keeps_summary_title(self):
        with patch.object(rm, '_res', return_value={'cost': 0, 'hours': 1, 'title': '무료 자료'}):
            out = rm.finish_option('A1', {'displayTitle': '  요약   제목 ', 'acts': [{'res': 'resource'}]}, 'api')
        self.assertEqual(out['displayTitle'], '요약 제목')
        self.assertEqual(out['acts'][0]['res'], 'resource')


if __name__ == '__main__':
    unittest.main()