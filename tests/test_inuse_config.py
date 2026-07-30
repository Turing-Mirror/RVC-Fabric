# -*- coding: utf-8 -*-
"""sanitize_inuse_dict must keep safe float keys like in_gain_db."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from inuse_template import CLEAN_INUSE, sanitize_inuse_dict


class InuseSanitizeTests(unittest.TestCase):
    def test_clean_template_has_in_gain_db(self):
        self.assertIn("in_gain_db", CLEAN_INUSE)
        self.assertEqual(CLEAN_INUSE["in_gain_db"], 0.0)

    def test_preserves_user_in_gain_db(self):
        cleaned, notes = sanitize_inuse_dict({"in_gain_db": 6.0, "pitch": 3})
        self.assertEqual(cleaned["in_gain_db"], 6.0)
        self.assertEqual(cleaned["pitch"], 3)
        self.assertEqual(notes, [])


if __name__ == "__main__":
    unittest.main()
