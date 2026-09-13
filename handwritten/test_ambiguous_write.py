"""Minimal handwritten AUT regression. test_origin: handwritten.

Imports the notifier, not the grader. Labeled handwritten in VerificationRecord.
"""
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
from invariant.hashing import hash_file
from invariant.models import ExecutionResultClass, TestOrigin, VerificationRecord
from invariant.verification import records_bind

DESTINATION = "C-RELEASES"
OPERATION_ID = "release-note-v42"
CONTENT = "Release v42 shipped to production."
TEST_ORIGIN = TestOrigin.HANDWRITTEN
TEST_HASH = hash_file(Path(__file__))


def _run(policy: str, fault: str | None, query: str | None):
    adapter, observer, _store = make_session()
    adapter.arm_send(fault)
    adapter.arm_query(query)
    report = ReleaseNotifier(adapter).announce(DESTINATION, OPERATION_ID, CONTENT, recovery=policy)
    return observer, report


class HandwrittenAutRegression(unittest.TestCase):
    def test_origin_is_handwritten(self):
        record = VerificationRecord(
            workflow_id="wf-release-v42",
            run_attempt=1,
            aut_revision="local",
            generated_test_hash=TEST_HASH,
            required_outcomes={"named_assertion": "no_duplicate_for_operation"},
            result_class=ExecutionResultClass.INTENDED_ASSERTION_FAILED,
            named_assertion="no_duplicate_for_operation",
            test_origin=TEST_ORIGIN,
        )
        self.assertEqual(record.test_origin, TestOrigin.HANDWRITTEN)
        self.assertTrue(records_bind(record, record))

    def test_original_bug_is_a_finding(self):
        observer, report = _run("blind_retry", "commit_drop_ack", None)
        result = no_duplicate_for_operation(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_FAILED)

    def test_correct_recovery_committed(self):
        observer, report = _run("reconcile", "commit_drop_ack", "complete")
        result = committed_resolved_once(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)

    def test_correct_send_once_when_never_dispatched(self):
        observer, report = _run("reconcile", "block_before_dispatch", None)
        result = completes_missing_work(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)

    def test_unknown_not_complete(self):
        observer, report = _run("reconcile", "commit_drop_ack", "truncated_empty")
        result = unknown_after_ambiguous_dispatch(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.application_outcome.value, "unknown")
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)

    def test_legitimate_new_operation_same_text(self):
        adapter, observer, _store = make_session()
        notifier = ReleaseNotifier(adapter)
        notifier.announce(DESTINATION, OPERATION_ID, CONTENT, recovery="reconcile")
        report = notifier.announce(DESTINATION, OPERATION_ID + "-followup", CONTENT, recovery="reconcile")
        result = legitimate_second_op_allowed(
            observer, DESTINATION, OPERATION_ID + "-followup", CONTENT, report
        )
        self.assertEqual(observer.count(DESTINATION, OPERATION_ID, CONTENT), 1)
        self.assertEqual(observer.count(DESTINATION, OPERATION_ID + "-followup", CONTENT), 1)
        self.assertEqual(observer.count_content(DESTINATION, CONTENT), 2)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)


if __name__ == "__main__":
    unittest.main()
