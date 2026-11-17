import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import popup


class PopupContractTest(unittest.TestCase):
    def test_warn_uses_main_card_size(self):
        self.assertEqual(popup.WARN_SIZE, popup.MAIN_SIZE)

    def test_autoclose_is_thirty_seconds(self):
        self.assertEqual(popup.AUTOCLOSE_MS, 30_000)

    def test_accent_colors_defined(self):
        self.assertTrue(popup.ACCENT.startswith("#"))
        self.assertTrue(popup.CARD_BG.startswith("#"))


class FinishTest(unittest.TestCase):
    class FakeRoot:
        def __init__(self):
            self.after_calls = []
            self.destroyed = False

        def after_idle(self, fn):
            self.after_calls.append(fn)

        def destroy(self):
            self.destroyed = True

    def test_finish_defers_destroy_and_sets_result(self):
        root = self.FakeRoot()
        popup._finish(root, "snooze")
        self.assertEqual(root.result, "snooze")
        self.assertFalse(root.destroyed)
        self.assertEqual(len(root.after_calls), 1)
        root.after_calls[0]()
        self.assertTrue(root.destroyed)

    def test_finish_is_idempotent(self):
        root = self.FakeRoot()
        popup._finish(root, "ack")
        popup._finish(root, "snooze")
        self.assertEqual(root.result, "ack")
        self.assertEqual(len(root.after_calls), 1)
