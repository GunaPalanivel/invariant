"""Holdout ExpectedIntent was authored independently and is scored separately."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invariant.hashing import sha256_text
from invariant.models import ExpectedIntent, TestOrigin
from invariant.runner import result_matches_required, run_expected_cases


class TestHoldout(unittest.TestCase):
    def test_holdout_intent_is_a_different_operation(self):
        primary = ExpectedIntent.from_path(ROOT / "cases" / "e4" / "expected_intent.json")
        holdout = ExpectedIntent.from_path(ROOT / "cases" / "holdout" / "expected_intent.json")
        self.assertNotEqual(primary.operation_id, holdout.operation_id)
        self.assertNotEqual(primary.destination, holdout.destination)

    def test_holdout_required_outcomes(self):
        holdout = ExpectedIntent.from_path(ROOT / "cases" / "holdout" / "expected_intent.json")
        executions = run_expected_cases(
            holdout,
            test_origin=TestOrigin.GENERATED,
            test_hash=sha256_text("holdout"),
            workflow_id="wf-holdout-changelog",
        )
        for item in executions:
            self.assertTrue(result_matches_required(item), item.case_id)
