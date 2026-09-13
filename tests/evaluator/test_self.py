"""Evaluator self-tests — separate from AUT regressions."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invariant.evaluate import detections, pack_valid
from invariant.hashing import sha256_text
from invariant.models import ExecutionResultClass, ExpectedIntent, TestOrigin
from invariant.runner import run_expected_cases


class TestEvaluatorSelf(unittest.TestCase):
    def test_detections_count_result_classes(self):
        intent = ExpectedIntent.from_path(ROOT / "cases" / "e4" / "expected_intent.json")
        executions = run_expected_cases(
            intent,
            test_origin=TestOrigin.GENERATED,
            test_hash=sha256_text("self"),
            workflow_id="wf-self",
        )
        counts = detections(executions)
        self.assertEqual(counts[ExecutionResultClass.INVALID_TEST.value], 0)
        self.assertGreaterEqual(counts[ExecutionResultClass.INTENDED_ASSERTION_FAILED.value], 3)
        self.assertTrue(pack_valid(executions, matrix={"ok": True})["valid"])
        self.assertTrue(pack_valid(executions)["checker_ok"])
        self.assertFalse(pack_valid(executions)["valid"])
