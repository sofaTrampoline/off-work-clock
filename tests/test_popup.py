import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import popup


class PopupContractTest(unittest.TestCase):
    def test_warn_card_is_shorter(self):
        self.assertLess(popup.WARN_SIZE[1], popup.MAIN_SIZE[1])

    def test_warn_autoclose_is_thirty_seconds(self):
        self.assertEqual(popup.WARN_AUTOCLOSE_MS, 30_000)

    def test_accent_colors_defined(self):
        self.assertTrue(popup.ACCENT.startswith("#"))
        self.assertTrue(popup.CARD_BG.startswith("#"))
