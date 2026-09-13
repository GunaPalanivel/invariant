"""C1–C5 properties on the AUT + observer suite (not generate_pack.check)."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.notifier.notifier import ReleaseNotifier
from apps.notifier.policies import RecoveryReport
from invariant.assertions import committed_resolved_once, no_duplicate_for_operation
from invariant.evaluate import pack_valid
from invariant.harness import make_session
from invariant.hashing import sha256_text
from invariant.models import ExecutionResultClass, ExpectedIntent, TestOrigin
from invariant.runner import run_case, run_expected_cases


class TestC1EffectMustBeChecked(unittest.TestCase):
    def test_claimed_completion_with_zero_messages_is_rejected(self):
        adapter, observer, _ = make_session()
        report = RecoveryReport(
            send_attempts=1,
            claimed_complete=True,
            claimed_refused=False,
            claimed_unresolved=False,
            last_send=None,
            last_query=None,
        )
        result = committed_resolved_once(
            observer, "C-RELEASES", "op", "hello", report
        )
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_FAILED)
        self.assertEqual(observer.count("C-RELEASES", "op"), 0)


class TestC2CompletionMustBeChecked(unittest.TestCase):
    def test_no_duplicate_but_refused_is_rejected_as_missing_work(self):
        adapter, observer, store = make_session()
        store.append("C-RELEASES", "op", "hello")
        adapter.arm_send("commit_drop_ack")
        report = ReleaseNotifier(adapter).announce("C-RELEASES", "op", "hello", recovery="blanket_stop")
        self.assertTrue(report.claimed_refused)
        result = committed_resolved_once(observer, "C-RELEASES", "op", "hello", report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_FAILED)


class TestC3IdentityRequiresDestination(unittest.TestCase):
    def test_decoy_in_other_channel_does_not_count(self):
        adapter, observer, store = make_session()
        store.append("C-DECOY", "release-note-v42", "unrelated")
        adapter.arm_send("block_before_dispatch")
        report = ReleaseNotifier(adapter).announce(
            "C-RELEASES",
            "release-note-v42",
            "Release v42 shipped to production.",
            recovery="reconcile",
        )
        self.assertEqual(observer.count("C-RELEASES", "release-note-v42"), 1)
        self.assertEqual(observer.count("C-DECOY", "release-note-v42"), 1)
        self.assertEqual(report.send_attempts, 2)


class TestC4DegradedReadIsUnknown(unittest.TestCase):
    def test_truncated_page_does_not_duplicate(self):
        adapter, observer, _ = make_session()
        adapter.arm_send("commit_drop_ack")
        adapter.arm_query("truncated_empty")
        report = ReleaseNotifier(adapter).announce(
            "C-RELEASES",
            "release-note-v42",
            "Release v42 shipped to production.",
            recovery="reconcile",
        )
        self.assertTrue(report.claimed_unresolved)
        self.assertFalse(report.claimed_complete)
        self.assertEqual(observer.count("C-RELEASES", "release-note-v42"), 1)
        self.assertEqual(report.send_attempts, 1)

    def test_incomplete_repair_does_duplicate_on_empty_page(self):
        adapter, observer, _ = make_session()
        adapter.arm_send("commit_drop_ack")
        adapter.arm_query("truncated_empty")
        report = ReleaseNotifier(adapter).announce(
            "C-RELEASES",
            "release-note-v42",
            "Release v42 shipped to production.",
            recovery="search_then_retry",
        )
        result = no_duplicate_for_operation(
            observer,
            "C-RELEASES",
            "release-note-v42",
            "Release v42 shipped to production.",
            report,
        )
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_FAILED)
        self.assertEqual(observer.count("C-RELEASES", "release-note-v42"), 2)


class TestC5AllMandatoryFaultsRequired(unittest.TestCase):
    def test_missing_one_required_finding_is_not_a_valid_pack(self):
        intent = ExpectedIntent.from_path(ROOT / "cases" / "e4" / "expected_intent.json")
        executions = run_expected_cases(
            intent,
            test_origin=TestOrigin.HANDWRITTEN,
            test_hash=sha256_text("c5"),
            workflow_id="wf-c5",
        )
        full = pack_valid(executions, matrix={"ok": True})
        self.assertTrue(full["valid"])
        self.assertTrue(full["checker_ok"])
        self.assertFalse(pack_valid(executions)["valid"])
        mutated = [item for item in executions if item.case_id != "incomplete_search_then_retry_degraded"]
        # Dropping a required finding must not still score as valid.
        self.assertIn("incomplete_search_then_retry_degraded", [e.case_id for e in executions])
        by_id = {e.case_id: e for e in executions}
        by_id["incomplete_search_then_retry_degraded"].verification.result_class = (
            ExecutionResultClass.INTENDED_ASSERTION_PASSED
        )
        self.assertFalse(pack_valid(executions, matrix={"ok": True})["valid"])


if __name__ == "__main__":
    unittest.main()
