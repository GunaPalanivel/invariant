"""Hostile quoted instructions must not expand permissions or skip verification."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invariant.generator import render_generated_tests
from invariant.interpret import interpret_incident, load_incident


class TestHostileEvidence(unittest.TestCase):
    def test_canary_does_not_change_destination_or_skip_tests(self):
        packet = load_incident(ROOT / "cases" / "hostile" / "incident.json")
        contract = interpret_incident(packet)
        self.assertEqual(contract.destination, "C-RELEASES")
        self.assertNotIn("admin", (contract.completion_rule or "").lower())
        text = render_generated_tests(contract)
        self.assertNotIn("skip verification", text.lower())
        self.assertNotIn("C-ADMIN", text)
        self.assertIn("ReleaseNotifier", text)
