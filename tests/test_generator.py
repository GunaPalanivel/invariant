"""Generated tests import the notifier and cover the required cases."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invariant.generator import render_generated_tests, write_generated_tests, write_weak_control
from invariant.interpret import interpret_incident, load_incident


class TestGenerator(unittest.TestCase):
    def test_generated_source_imports_notifier_not_expected_intent(self):
        packet = load_incident(ROOT / "cases" / "e4" / "incident.json")
        contract = interpret_incident(packet)
        text = render_generated_tests(contract)
        self.assertIn("from apps.notifier.notifier import ReleaseNotifier", text)
        self.assertNotIn("ExpectedIntent", text)
        self.assertNotIn("generate_pack", text)
        self.assertIn("test_original_bug_duplicate_is_a_finding", text)
        self.assertIn("test_incomplete_repair_empty_page_is_a_finding", text)
        self.assertIn("test_unknown_after_dispatch_incomplete_read", text)

    def test_ungrounded_contract_does_not_fabricate_pack(self):
        packet = load_incident(ROOT / "cases" / "e4" / "incident.json")
        contract = interpret_incident(packet)
        contract.grounded = False
        with self.assertRaises(ValueError):
            render_generated_tests(contract)

    def test_template_pack_executes_on_the_aut(self):
        packet = load_incident(ROOT / "cases" / "e4" / "incident.json")
        contract = interpret_incident(packet)
        from invariant.generator import generated_pack_executes, render_generated_tests

        ok, reason = generated_pack_executes(render_generated_tests(contract))
        self.assertTrue(ok, reason)
        packet = load_incident(ROOT / "cases" / "e4" / "incident.json")
        contract = interpret_incident(packet)
        from invariant.generator import generate_pack

        result = generate_pack(contract, llm=None)
        self.assertEqual(result.origin, "disclosed_template")
        self.assertFalse(result.invalid_test)
        packet = load_incident(ROOT / "cases" / "e4" / "incident.json")
        contract = interpret_incident(packet)
        path = write_weak_control(contract, ROOT / "generated" / "test_weak_response_only.py")
        text = path.read_text(encoding="utf-8")
        self.assertIn("weak_control", text)
        self.assertIn("Labeled weak", text)
