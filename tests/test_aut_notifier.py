"""AUT-bound tests for the ambiguous-write family. Import the notifier, not a grader."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.notifier.notifier import ReleaseNotifier
from invariant.assertions import (
    committed_resolved_once,
    completes_missing_work,
    legitimate_second_op_allowed,
    no_duplicate_for_operation,
    unknown_after_ambiguous_dispatch,
)
from invariant.harness import make_session
from invariant.models import ExecutionResultClass, ExpectedIntent, TestOrigin
from invariant.runner import result_matches_required, run_expected_cases
from invariant.hashing import sha256_text


class TestAutNotifier(unittest.TestCase):
    def test_imports_notifier_entrypoint(self):
        self.assertTrue(hasattr(ReleaseNotifier, "announce"))

    def test_original_retry_is_detection(self):
        adapter, observer, _ = make_session()
        adapter.arm_send("commit_drop_ack")
        report = ReleaseNotifier(adapter).announce(
            "C-RELEASES", "release-note-v42", "Release v42 shipped to production.", recovery="blind_retry"
        )
        result = no_duplicate_for_operation(
            observer, "C-RELEASES", "release-note-v42", "Release v42 shipped to production.", report
        )
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_FAILED)
        self.assertGreater(observer.count("C-RELEASES", "release-note-v42"), 1)

    def test_blanket_stop_missing_work_is_detection(self):
        adapter, observer, _ = make_session()
        adapter.arm_send("block_before_dispatch")
        report = ReleaseNotifier(adapter).announce(
            "C-RELEASES", "release-note-v42", "Release v42 shipped to production.", recovery="blanket_stop"
        )
        result = completes_missing_work(
            observer, "C-RELEASES", "release-note-v42", "Release v42 shipped to production.", report
        )
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_FAILED)
        self.assertEqual(observer.count("C-RELEASES", "release-note-v42"), 0)

    def test_correct_committed_no_duplicate(self):
        adapter, observer, _ = make_session()
        adapter.arm_send("commit_drop_ack")
        report = ReleaseNotifier(adapter).announce(
            "C-RELEASES", "release-note-v42", "Release v42 shipped to production.", recovery="reconcile"
        )
        result = committed_resolved_once(
            observer, "C-RELEASES", "release-note-v42", "Release v42 shipped to production.", report
        )
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)
        self.assertEqual(observer.count("C-RELEASES", "release-note-v42"), 1)

    def test_correct_never_dispatched_send_once(self):
        adapter, observer, _ = make_session()
        adapter.arm_send("block_before_dispatch")
        report = ReleaseNotifier(adapter).announce(
            "C-RELEASES", "release-note-v42", "Release v42 shipped to production.", recovery="reconcile"
        )
        result = completes_missing_work(
            observer, "C-RELEASES", "release-note-v42", "Release v42 shipped to production.", report
        )
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)
        self.assertEqual(observer.count("C-RELEASES", "release-note-v42"), 1)

    def test_legitimate_new_operation_same_text(self):
        adapter, observer, _ = make_session()
        report = ReleaseNotifier(adapter).announce(
            "C-RELEASES",
            "release-note-v42-followup",
            "Release v42 shipped to production.",
            recovery="reconcile",
        )
        result = legitimate_second_op_allowed(
            observer,
            "C-RELEASES",
            "release-note-v42-followup",
            "Release v42 shipped to production.",
            report,
        )
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)

    def test_dispatch_empty_read_unknown_no_second_write(self):
        adapter, observer, _ = make_session()
        adapter.arm_send("commit_drop_ack")
        adapter.arm_query("truncated_empty")
        report = ReleaseNotifier(adapter).announce(
            "C-RELEASES", "release-note-v42", "Release v42 shipped to production.", recovery="reconcile"
        )
        result = unknown_after_ambiguous_dispatch(
            observer, "C-RELEASES", "release-note-v42", "Release v42 shipped to production.", report
        )
        self.assertEqual(result.application_outcome.value, "unknown")
        self.assertEqual(report.send_attempts, 1)
        self.assertEqual(observer.count("C-RELEASES", "release-note-v42"), 1)
        self.assertFalse(result.passed is False and result.result_class.value == "intended_assertion_failed")
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)

    def test_expected_intent_suite_matches(self):
        intent = ExpectedIntent.from_path(ROOT / "cases" / "e4" / "expected_intent.json")
        executions = run_expected_cases(
            intent,
            test_origin=TestOrigin.HANDWRITTEN,
            test_hash=sha256_text("handwritten-suite"),
            workflow_id="wf-release-v42",
        )
        for item in executions:
            self.assertTrue(result_matches_required(item), item.case_id)


if __name__ == "__main__":
    unittest.main()
