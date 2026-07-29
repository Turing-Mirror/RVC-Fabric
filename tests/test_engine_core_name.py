# -*- coding: utf-8 -*-
"""engine-core cache path uses basename only (review #25)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _safe_engine_core_name(raw: str) -> str:
    """Mirror launcher.engine_core cache-name rule (no network)."""
    safe = Path(str(raw or "engine-core.zip")).name
    if not safe or safe in (".", "..") or ".." in safe:
        return "engine-core.zip"
    return safe


class EngineCoreNameTests(unittest.TestCase):
    def test_path_segments_stripped_to_basename(self):
        for raw, expect in (
            ("engine-core.zip", "engine-core.zip"),
            ("assets/core/engine-core-x.zip", "engine-core-x.zip"),
            ("..\\evil.zip", "evil.zip"),
            ("", "engine-core.zip"),
            (".", "engine-core.zip"),
        ):
            self.assertEqual(_safe_engine_core_name(raw), expect, msg=raw)


if __name__ == "__main__":
    unittest.main()
