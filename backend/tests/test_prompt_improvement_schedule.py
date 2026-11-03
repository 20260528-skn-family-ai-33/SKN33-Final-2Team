from datetime import datetime, timezone
from unittest import TestCase
from app.services.prompt_improvement_schedule import KST, monthly_run_at, next_run_after, run_key


class PromptImprovementScheduleTests(TestCase):
    def test_first_monday_and_six_am_for_every_month(self):
        for year in (2026, 2027, 2028):
            for month in range(1, 13):
                value = monthly_run_at(year, month)
                self.assertEqual(value.weekday(), 0)
                self.assertTrue(1 <= value.day <= 7)
                self.assertEqual(value.hour, 6)
                self.assertEqual(value.tzinfo, KST)

    def test_next_execution_and_year_boundary(self):
        self.assertEqual(next_run_after(datetime(2026, 11, 1, tzinfo=KST)), datetime(2026, 11, 2, 6, tzinfo=KST))
        self.assertEqual(next_run_after(datetime(2026, 11, 2, 6, tzinfo=KST)), datetime(2026, 12, 7, 6, tzinfo=KST))
        self.assertEqual(next_run_after(datetime(2026, 12, 31, tzinfo=KST)), datetime(2027, 1, 4, 6, tzinfo=KST))

    def test_utc_converts_to_local_month_and_same_month_has_one_key(self):
        value = datetime(2026, 10, 31, 22, tzinfo=timezone.utc)
        self.assertEqual(run_key(value), 'prompt-improvement/2026-11')
        self.assertEqual(run_key(value), run_key(datetime(2026, 11, 30, tzinfo=KST)))

    def test_naive_times_are_rejected(self):
        for function in (next_run_after, run_key):
            with self.assertRaises(ValueError):
                function(datetime(2026, 11, 1))
