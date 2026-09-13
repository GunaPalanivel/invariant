"""Generated AUT regression. test_origin: generated.

Imports the notifier entrypoint. Does not import scoring keys or grader checks.
"""
from __future__ import annotations

import unittest

from apps.notifier.notifier import ReleaseNotifier
from invariant.assertions import (
    committed_resolved_once,
    completes_missing_work,
    legitimate_second_op_allowed,
    no_duplicate_for_operation,
    unknown_after_ambiguous_dispatch,
)
from invariant.harness import make_session
from invariant.models import ExecutionResultClass

DESTINATION = 'C-RELEASES'
OPERATION_ID = 'release-note-v42'
CONTENT = 'Release v42 shipped to production.'
CONTRACT_HASH = '02707a09c0cfd47f2a7b681381ae69cfbbd9d1ac3a8f471d5d03ea43260bb140'


def _run(policy: str, fault: str | None, query: str | None, operation_id: str = OPERATION_ID):
    adapter, observer, _store = make_session()
    adapter.arm_send(fault)
    adapter.arm_query(query)
    report = ReleaseNotifier(adapter).announce(DESTINATION, operation_id, CONTENT, recovery=policy)
    return adapter, observer, report


class GeneratedAutRegression(unittest.TestCase):
    def test_original_bug_duplicate_is_a_finding(self):
        _adapter, observer, report = _run("blind_retry", "commit_drop_ack", None)
        result = no_duplicate_for_operation(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_FAILED)

    def test_incomplete_repair_empty_page_is_a_finding(self):
        _adapter, observer, report = _run("search_then_retry", "commit_drop_ack", "truncated_empty")
        result = no_duplicate_for_operation(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_FAILED)

    def test_blanket_stop_leaves_missing_work(self):
        _adapter, observer, report = _run("blanket_stop", "block_before_dispatch", None)
        result = completes_missing_work(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_FAILED)

    def test_correct_committed_no_duplicate(self):
        _adapter, observer, report = _run("reconcile", "commit_drop_ack", "complete")
        result = committed_resolved_once(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)

    def test_correct_never_dispatched_send_once(self):
        _adapter, observer, report = _run("reconcile", "block_before_dispatch", None)
        result = completes_missing_work(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)

    def test_legitimate_new_operation_same_text(self):
        new_op = OPERATION_ID + "-followup"
        _adapter, observer, report = _run("reconcile", None, None, operation_id=new_op)
        result = legitimate_second_op_allowed(observer, DESTINATION, new_op, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)

    def test_unknown_after_dispatch_incomplete_read(self):
        _adapter, observer, report = _run("reconcile", "commit_drop_ack", "truncated_empty")
        result = unknown_after_ambiguous_dispatch(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)
        self.assertEqual(result.application_outcome.value, "unknown")
        self.assertEqual(observer.count(DESTINATION, OPERATION_ID, CONTENT), 1)
        self.assertEqual(report.send_attempts, 1)


if __name__ == "__main__":
    unittest.main()
