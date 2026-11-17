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


class TaskCommandTest(unittest.TestCase):
    def test_command_has_fire_and_clock(self):
        cmd = off_work._task_command("main", "18:30")
        self.assertIn("--fire main", cmd)
        self.assertIn("--clock 18:30", cmd)
        self.assertIn("off_work.py", cmd)

    def test_command_uses_pythonw_when_available(self):
        cmd = off_work._task_command("warn", "18:20")
        self.assertIn(off_work._pythonw(), cmd)


class StateFileTest(unittest.TestCase):
    def test_roundtrip(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".state.json"
            off_work._save_task_names(["a", "b"], p)
            self.assertEqual(off_work._load_task_names(p), ["a", "b"])

    def test_missing_file_returns_empty(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(off_work._load_task_names(Path(d) / "nope.json"), [])


class FireArgsTest(unittest.TestCase):
    def test_parse_kind_and_clock(self):
        kind, clock = off_work.parse_fire_args(
            ["--fire", "main", "--clock", "18:30"]
        )
        self.assertEqual(kind, "main")
        self.assertEqual(clock, "18:30")

    def test_warn_kind(self):
        kind, _ = off_work.parse_fire_args(["--fire", "warn", "--clock", "18:20"])
        self.assertEqual(kind, "warn")

    def test_defaults(self):
        kind, clock = off_work.parse_fire_args(["--fire"])
        self.assertEqual(kind, "main")
        self.assertEqual(clock, "")
