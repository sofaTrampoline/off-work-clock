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

    def test_triggers_on_target_minute(self):
        now = datetime(2026, 11, 17, 9, 0)
        clock_out = datetime(2026, 11, 17, 18, 30, 45)
        warn, main = off_work.reminder_times(clock_out, now)
        self.assertEqual(main, datetime(2026, 11, 17, 18, 30))
        self.assertEqual(warn, datetime(2026, 11, 17, 18, 20))

    def test_trigger_falls_back_to_next_minute_when_minute_passed(self):
        now = datetime(2026, 11, 17, 18, 30, 10)
        clock_out = datetime(2026, 11, 17, 18, 30, 45)
        warn, main = off_work.reminder_times(clock_out, now)
        self.assertEqual(main, datetime(2026, 11, 17, 18, 31))
        self.assertIsNone(warn)


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


class QueryTaskNamesTest(unittest.TestCase):
    def test_parse_keeps_only_own_tasks_and_strips_backslash(self):
        sample = (
            '"\\OffWorkReminder_1752","2026/11/17 17:52:00","就绪"\r\n'
            '"\\OffWorkReminder_Warn_1747","2026/11/17 17:47:00","就绪"\r\n'
            '"\\StartVDriveSvr",N/A,"已禁用"\r\n'
            "\r\n"
        )
        self.assertEqual(
            off_work._parse_task_names(sample),
            ["OffWorkReminder_1752", "OffWorkReminder_Warn_1747"],
        )

    def test_parse_skips_blank_and_malformed_lines(self):
        self.assertEqual(off_work._parse_task_names("\n  \nbroken\n"), [])

    def test_schedule_deletes_stale_tasks_from_query(self):
        import contextlib
        import io
        from unittest import mock

        stale = ["OffWorkReminder_1700", "OffWorkReminder_Warn_1650"]
        with mock.patch.object(off_work, "_load_task_names", return_value=[]), \
                mock.patch.object(off_work, "_query_task_names", return_value=stale), \
                mock.patch.object(off_work, "_delete_tasks") as delete, \
                mock.patch.object(off_work, "_create_task", return_value=True) as create, \
                mock.patch.object(off_work, "_save_task_names"), \
                mock.patch("off_work.datetime") as dt:
            dt.now.return_value = datetime(2026, 11, 17, 9, 0)
            with contextlib.redirect_stdout(io.StringIO()):
                off_work.schedule_notification(datetime(2026, 11, 17, 18, 30, 37))

        delete.assert_called_once()
        self.assertEqual(sorted(delete.call_args[0][0]), stale)
        commands = [call.args[2] for call in create.call_args_list]
        self.assertEqual(len(commands), 2)
        for cmd in commands:
            self.assertTrue(cmd.endswith("--clock 18:30:37"), cmd)


class PopupTargetTest(unittest.TestCase):
    def test_main_target_is_clock_time(self):
        now = datetime(2026, 11, 17, 9, 0)
        self.assertEqual(
            off_work._popup_target("main", "17:51:21", now),
            datetime(2026, 11, 17, 17, 51, 21),
        )

    def test_warn_target_is_ten_minutes_earlier(self):
        now = datetime(2026, 11, 17, 9, 0)
        self.assertEqual(
            off_work._popup_target("warn", "17:51:21", now),
            datetime(2026, 11, 17, 17, 41, 21),
        )

    def test_clock_text_without_seconds(self):
        now = datetime(2026, 11, 17, 9, 0)
        self.assertEqual(
            off_work._popup_target("main", "17:52", now),
            datetime(2026, 11, 17, 17, 52),
        )

    def test_invalid_clock_text_returns_none(self):
        now = datetime(2026, 11, 17, 9, 0)
        self.assertIsNone(off_work._popup_target("main", "", now))
        self.assertIsNone(off_work._popup_target("main", "oops", now))


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


class CreateTaskArgvTest(unittest.TestCase):
    def test_argv_has_sd_date_st_time_and_it(self):
        from unittest import mock

        with mock.patch("off_work.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = ""
            run.return_value.stderr = ""
            ok = off_work._create_task(
                "OffWorkReminder_Test", datetime(2026, 11, 18, 7, 45), "cmd"
            )
        self.assertTrue(ok)
        argv = run.call_args[0][0]
        self.assertEqual(argv[argv.index("/tn") + 1], "OffWorkReminder_Test")
        self.assertEqual(argv[argv.index("/st") + 1], "07:45")
        self.assertIn("/it", argv)
        self.assertTrue(argv[argv.index("/sd") + 1])
        self.assertIn("2026", argv[argv.index("/sd") + 1])

    def test_failure_returns_false(self):
        from unittest import mock

        with mock.patch("off_work.subprocess.run") as run:
            run.return_value.returncode = 1
            run.return_value.stdout = ""
            run.return_value.stderr = "boom"
            self.assertFalse(
                off_work._create_task(
                    "X", datetime(2026, 11, 18, 7, 45), "cmd"
                )
            )


class FireSnoozeTest(unittest.TestCase):
    def test_snooze_schedules_task_with_original_clock(self):
        import types
        from unittest import mock

        fake_popup = types.SimpleNamespace(
            run_popup=lambda kind, clock: "snooze"
        )
        with mock.patch.dict(sys.modules, {"popup": fake_popup}), \
                mock.patch.object(off_work, "_create_task", return_value=True) as create, \
                mock.patch.object(off_work, "_load_task_names", return_value=[]), \
                mock.patch.object(off_work, "_wait_until") as wait, \
                mock.patch.object(off_work, "_save_task_names") as save:
            off_work._fire("main", "18:30")

        self.assertEqual(wait.call_count, 1)
        self.assertEqual(wait.call_args[0][0].strftime("%H:%M"), "18:30")

        create.assert_called_once()
        name, when, command = create.call_args[0]
        self.assertTrue(name.startswith("OffWorkReminder_Snooze_"))
        self.assertIn("--fire main", command)
        self.assertIn("--clock 18:30", command)
        save.assert_called_once()
