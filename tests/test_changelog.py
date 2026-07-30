# -*- coding: utf-8 -*-
"""Unit tests for launcher.online.changelog (no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.online.changelog import (
    ChangelogEntry,
    latest_entry,
    notes_from_entry,
    parse_changelog,
    sort_entries,
)


class ChangelogParseTests(unittest.TestCase):
    def test_parse_and_sort_newest_first(self):
        data = {
            "schema": 1,
            "entries": [
                {"version": "1.2.3", "body": "base", "date": "260730"},
                {
                    "version": "1.2.3-hotfix1",
                    "highlights": ["fix a"],
                    "body": "hotfix body",
                    "date": "260731",
                },
                {"version": "1.2.0", "body": "old"},
            ],
        }
        rows = parse_changelog(data)
        self.assertEqual([r.version for r in rows], ["1.2.3-hotfix1", "1.2.3", "1.2.0"])
        latest = latest_entry(rows)
        assert latest is not None
        self.assertEqual(latest.version, "1.2.3-hotfix1")
        self.assertIn("fix a", latest.summary)
        self.assertEqual(notes_from_entry(latest), "hotfix body")

    def test_reject_part_and_empty(self):
        rows = parse_changelog(
            [
                {"version": "1.2.3-part1", "body": "no"},
                {"version": "1.2.3", "body": ""},
                {"version": "1.2.4", "highlights": ["ok"]},
            ]
        )
        self.assertEqual([r.version for r in rows], ["1.2.4"])

    def test_display_title_fallback(self):
        e = ChangelogEntry.from_dict(
            {"version": "1.2.3-hotfix2", "body": "x"}
        )
        assert e is not None
        self.assertEqual(e.display_title, "1.2.3 热修2")


class ChangelogSortTests(unittest.TestCase):
    def test_numeric_version_order(self):
        rows = sort_entries(
            [
                ChangelogEntry(version="1.2.9", body="a"),
                ChangelogEntry(version="1.2.10", body="b"),
            ]
        )
        self.assertEqual(rows[0].version, "1.2.10")


if __name__ == "__main__":
    unittest.main()
