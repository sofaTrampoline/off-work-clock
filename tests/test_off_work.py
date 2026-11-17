import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import off_work


class CeilMinuteTest(unittest.TestCase):
    def test_exact_minute_unchanged(self):
        dt = datetime(2026, 11, 17, 18, 30, 0)
        self.assertEqual(off_work.ceil_minute(dt), dt)

    def test_seconds_round_up(self):
        dt = datetime(2026, 11, 17, 18, 30, 1)
        self.assertEqual(off_work.ceil_minute(dt), datetime(2026, 11, 17, 18, 31))


class ReminderTimesTest(unittest.TestCase):
    def test_warn_is_ten_minutes_before(self):
        now = datetime(2026, 11, 17, 9, 0)
        clock_out = datetime(2026, 11, 17, 18, 30)
        warn, main = off_work.reminder_times(clock_out, now)
        self.assertEqual(main, datetime(2026, 11, 17, 18, 30))
        self.assertEqual(warn, datetime(2026, 11, 17, 18, 20))

    def test_warn_skipped_when_passed(self):
        now = datetime(2026, 11, 17, 18, 25)
        clock_out = datetime(2026, 11, 17, 18, 30)
        warn, main = off_work.reminder_times(clock_out, now)
        self.assertIsNone(warn)
        self.assertEqual(main, datetime(2026, 11, 17, 18, 30))

    def test_rounds_up_to_next_minute(self):
        now = datetime(2026, 11, 17, 9, 0)
        clock_out = datetime(2026, 11, 17, 18, 30, 45)
        warn, main = off_work.reminder_times(clock_out, now)
        self.assertEqual(main, datetime(2026, 11, 17, 18, 31))
        self.assertEqual(warn, datetime(2026, 11, 17, 18, 21))
