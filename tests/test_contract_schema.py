"""Pydantic contract gate. Extra fields ignored; core fields mapped."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invariant.contract_schema import parse_contract_payload, parse_judge_payload


class TestContractSchema(unittest.TestCase):
    def test_parse_contract_keeps_core_fields(self):
        parsed = parse_contract_payload(
            {
                "destination": "C-RELEASES",
                "operation_id": "release-note-v42",
                "content": "Release v42 shipped to production.",
                "completion_rule": "at most one message",
                "source_spans": [{"field": "destination", "source": "slack", "excerpt": "C-RELEASES"}],
                "unexpected_model_key": "drop me",
            }
        )
        self.assertEqual(parsed["destination"], "C-RELEASES")
        self.assertNotIn("unexpected_model_key", parsed)

    def test_parse_judge(self):
        parsed = parse_judge_payload({"grounded": True, "reason": "ok", "ungrounded_fields": []})
        self.assertTrue(parsed["grounded"])
