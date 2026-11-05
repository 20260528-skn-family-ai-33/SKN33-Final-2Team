"""Track DB prompt routing and free-only contract; no model/network calls."""
import unittest
from unittest.mock import patch
from app import llm
from app.agents import roadmap as rm


class TrackPromptTests(unittest.TestCase):
    def test_all_tracks_use_db_system_text_without_code_policy_overwrite(self):
        prompt = '### GENERATION\nDB active generation\n### REVISION\nDB active revision'
        for pid in ('A1', 'A2', 'A3'):
            with patch.object(rm.db, 'all_', return_value=[{'system_prompt': prompt}]):
                self.assertEqual(rm._sys(pid, rm.R_SYS).split('\n[최신 Free Course 정책]')[0].split('\n\n[기간·비용 표시 계약')[0], 'DB active generation')
                self.assertEqual(rm._sys(pid, rm.REV_SYS).split('\n[최신 Free Course 정책]')[0].split('\n\n[기간·비용 표시 계약')[0], 'DB active revision')

    def test_db_generation_and_revision_are_selected(self):
        prompt = '### GENERATION\nDB generation\n### REVISION\nDB revision'
        with patch.object(rm.db, 'all_', return_value=[{'system_prompt': prompt}]) as query:
            generation = rm._sys('A1', rm.R_SYS)
            self.assertTrue(generation.startswith('DB generation'))
            self.assertIn('도서는 가격·예산과 무관', generation)
            self.assertTrue(rm._sys('A1', rm.REV_SYS).startswith('DB revision'))
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
                get_catalog.assert_called_once_with({}, None, free_only=pid == 'A1', track=pid)

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

    def test_free_prompt_wording_matches_course_filter_and_book_exception(self):
        from app.agents.roadmap_generation import POLICIES as generation
        from app.agents.roadmap_revision import POLICIES as revision
        from tools.install_track_prompts import POLICIES as install
        self.assertEqual(rm.PROMPT_VERSION, 'v2.6')
        for text in (rm.PERSPECTIVE_RULES['A1'], generation['A1'], revision['A1'], install['A1']):
            with self.subTest(policy=text):
                self.assertIn('강좌', text)
                self.assertIn('도서는 가격·예산과 무관하게 유료·가격 미확인', text)
                self.assertNotIn('무료 자료가 없을 때만', text)
                self.assertNotIn('유료 자료로 대체하지 않는다', text)

    def test_free_output_allows_paid_and_unknown_books(self):
        for cost in (100, None):
            with self.subTest(cost=cost), patch.object(rm, '_res', return_value={'type': 'book', 'cost': cost, 'hours': 1, 'title': '도서'}):
                out = rm.finish_option('A1', {'acts': [{'res': 'book'}]}, 'api')
                self.assertEqual(out['acts'][0]['res'], 'book')


if __name__ == '__main__':
    unittest.main()
