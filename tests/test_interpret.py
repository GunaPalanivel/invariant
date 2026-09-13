"""Interpreter + judge plumbing. Stub LLM; ExpectedIntent is not in the prompt."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invariant.interpret import (
    flatten_incident,
    heuristic_contract,
    interpret_incident,
    load_incident,
)
from invariant.llm import StubLLMClient


class TestInterpret(unittest.TestCase):
    def test_heuristic_contract_is_grounded_from_incident_packet(self):
        packet = load_incident(ROOT / "cases" / "e4" / "incident.json")
        contract = heuristic_contract(packet)
        self.assertTrue(contract.grounded, contract.ungrounded_fields)
        self.assertEqual(contract.destination, "C-RELEASES")
        self.assertEqual(contract.operation_id, "release-note-v42")
        self.assertEqual(contract.content, "Release v42 shipped to production.")

    def test_stub_llm_plan_then_judge(self):
        packet = load_incident(ROOT / "cases" / "e4" / "incident.json")
        raw = flatten_incident(packet)
        stub = StubLLMClient(
            {
                "Incident:": {
                    "destination": "C-RELEASES",
                    "operation_id": "release-note-v42",
                    "content": "Release v42 shipped to production.",
                    "completion_rule": "at most one message for that operation",
                    "source_spans": [
                        {
                            "field": "destination",
                            "source": "slack",
                            "locator": "1726200000.000100",
                            "excerpt": "C-RELEASES",
                        },
                        {
                            "field": "operation_id",
                            "source": "slack",
                            "excerpt": "release-note-v42",
                        },
                        {
                            "field": "content",
                            "source": "slack",
                            "excerpt": "Release v42 shipped to production.",
                        },
                        {
                            "field": "completion_rule",
                            "source": "linear",
                            "excerpt": "at most one message for that operation",
                        },
                    ],
                },
                "RAW PACKET:": {
                    "grounded": True,
                    "reason": "fields appear in the slack thread",
                    "ungrounded_fields": [],
                },
            }
        )
        contract = interpret_incident(packet, llm=stub)
        self.assertGreaterEqual(len(stub.calls), 2)
        self.assertTrue(contract.grounded)
        joined_prompts = "\n".join(user for _sys, user in stub.calls)
        self.assertIn("C-RELEASES", joined_prompts)
        self.assertNotIn("ExpectedIntent", joined_prompts)
        self.assertNotIn("required_result_class", joined_prompts)

    def test_intake_snowflake_is_not_aut_destination(self):
        packet = load_incident(ROOT / "cases" / "e4" / "incident.json")
        packet["slack_channel_id"] = "C0C1H02UHEW"
        contract = heuristic_contract(packet)
        self.assertEqual(contract.destination, "C-RELEASES")
        self.assertNotEqual(contract.destination, "C0C1H02UHEW")

    def test_hostile_quoted_destination_is_not_adopted(self):
        packet = load_incident(ROOT / "cases" / "hostile" / "incident.json")
        contract = interpret_incident(packet, llm=None)
        self.assertEqual(contract.destination, "C-RELEASES")
        self.assertNotEqual(contract.destination, "C-ADMIN")
