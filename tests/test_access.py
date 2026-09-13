"""M0 does not fake live three-app access."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invariant.access import probe


class TestAccess(unittest.TestCase):
    def test_missing_app_tokens_are_deferred(self):
        report = probe()
        self.assertIn(report["live_apps"]["slack"]["status"], {"deferred", "ready"})
        if not report["live_apps"]["slack"]["configured"]:
            self.assertEqual(report["live_apps"]["slack"]["status"], "deferred")
            self.assertEqual(report["three_app_eligibility"], "blocked")
        self.assertIn("local git", report["version_control"])
