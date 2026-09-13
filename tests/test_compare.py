"""Capable-agent comparison records an honest unfinished slot."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["INVARIANT_USE_LIVE_MODEL"] = "0"
os.environ["INVARIANT_WRITE_CONSOLE"] = "0"
os.environ["INVARIANT_WRITE_GENERATED"] = "0"

from invariant.compare import _weak_control_false_accepts_duplicate, compare


class TestCompare(unittest.TestCase):
    def test_weak_control_false_accepts_duplicate(self):
        weak = _weak_control_false_accepts_duplicate()
        self.assertTrue(weak["not_a_coding_agent"])
        self.assertTrue(weak["false_acceptance_of_original_bug"])

    def test_comparison_does_not_claim_superiority(self):
        report = compare()
        self.assertFalse(report["usefulness"]["superiority_claim"])
        self.assertEqual(report["capable_agent"]["status"], "unfinished")
        self.assertTrue(report["holdout"]["all_required_outcomes_met"])
        self.assertIn("reviewer", report["usefulness"]["invariant_minutes"].lower())
        self.assertNotRegex(report["usefulness"]["invariant_minutes"], r"^\d+(\.\d+)?$")
