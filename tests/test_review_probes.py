"""Desired-state tests for the eight review findings. Offline fakes only."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["INVARIANT_USE_LIVE_MODEL"] = "0"

from invariant import evaluate as ev
from invariant import generator as gen
from invariant import github_publish as gp
from invariant import live_publish as lp
from invariant import publication as pub
from invariant.interpret import interpret_incident, load_incident
from invariant.models import PublicationJournal

PACKET = load_incident(ROOT / "cases" / "e4" / "incident.json")
CONTRACT = interpret_incident(PACKET)
NOOP = """import unittest
from apps.notifier.notifier import ReleaseNotifier
from invariant.harness import make_session
class EmptyCoverage(unittest.TestCase):
    def test_one(self): self.assertTrue(True)
    def test_two(self): self.assertTrue(True)
    def test_three(self): self.assertTrue(True)
"""


class TestReviewFindings(unittest.TestCase):
    def test_f1_noop_is_invalid_and_does_not_validate_pack(self):
        class Stub:
            provider = "offline-probe"

            def complete_text(self, *args, **kwargs):
                self.prompt = args[1]
                return NOOP

        stub = Stub()
        result = gen.generate_pack(CONTRACT, stub)
        self.assertTrue(result.invalid_test)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(ev, "RESULTS", Path(tmp)), \
             patch.object(ev, "write_access"), \
             patch.object(ev, "interpret_incident_auto", return_value=(CONTRACT, "offline-probe", {})), \
             patch.object(ev, "try_live_client", return_value=None), \
             patch.object(ev, "write_generated_tests", return_value=result), \
             patch.object(ev, "write_weak_control"), \
             patch.object(ev, "publish_local", return_value=PublicationJournal(run_id="probe")), \
             patch.object(ev, "write_console_runs"):
            data = ev.evaluate()
        self.assertFalse(data["pack"]["valid"] and not result.invalid_test)
        if result.text == NOOP:
            self.assertFalse(data["pack"]["valid"])

    def test_f2_candidate_does_not_see_broker_canary(self):
        candidate = NOOP.replace(
            "self.assertTrue(True)",
            "self.assertEqual(__import__('os').environ.get('INVARIANT_REVIEW_CANARY'), 'synthetic-only')",
        )
        with patch.dict(os.environ, {"INVARIANT_REVIEW_CANARY": "synthetic-only"}):
            syntax, _ = gen.validate_generated_python(candidate)
            executed, reason = gen.generated_pack_executes(candidate)
        self.assertTrue(syntax)
        self.assertFalse(executed, reason)

    def test_f3_invented_fields_without_spans_are_ungrounded(self):
        class Stub:
            def complete_json(self, system, user):
                if "grounding judge" in system:
                    return {"grounded": True, "reason": "stub deliberately wrong", "ungrounded_fields": []}
                return {
                    "destination": PACKET["slack_channel_id"],
                    "operation_id": "invented-operation-992",
                    "content": "This fabricated body is absent from the incident.",
                    "completion_rule": "Invented rule",
                    "source_spans": [],
                }

        derived = interpret_incident(PACKET, Stub())
        self.assertFalse(derived.grounded)
        self.assertIn("operation_id", derived.ungrounded_fields)

    def test_f4_ci_bind_reads_remote_blob(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(pub, "RUNS_DIR", Path(tmp) / "runs"), \
             patch.object(gp, "ROOT", Path(tmp)), \
             patch.object(gp.github, "split_repo", return_value=("probe", "repo")), \
             patch.object(gp.github, "actions_runs_for_sha", return_value=[{
                 "id": 7, "head_sha": "a" * 40, "status": "completed", "conclusion": "failure",
                 "html_url": "https://example.invalid/ci/7"}]), \
             patch.object(gp.github, "list_run_artifacts", return_value=[]), \
             patch.object(gp.github, "get_contents") as get_contents:
            get_contents.side_effect = RuntimeError("no blob")
            journal = PublicationJournal(run_id="probe", github_head_sha="a" * 40)
            result = gp.wait_and_bind_ci(journal, "unverified-caller-supplied-hash", timeout_s=1)
        self.assertTrue(get_contents.call_count >= 1)
        self.assertFalse(result.ci_bound)

    def test_f5_slack_does_not_retry_ambiguous_error(self):
        effects = []

        def post(channel, text, **kwargs):
            effects.append({"channel": channel, "text": text})
            raise lp.slack_ad.SlackError("HTTP 500 after controlled fake commit")

        with tempfile.TemporaryDirectory() as tmp, patch.object(pub, "RUNS_DIR", Path(tmp)), \
             patch.object(lp.slack_ad, "chat_post_message", side_effect=post):
            _, evidence = lp.publish_slack_finding(
                PublicationJournal(run_id="probe"),
                channel="C012345",
                thread_ts="11.1",
                text="synthetic finding",
                operation_id="review-op",
            )
            persisted = pub.load_journal("probe").slack_reply_status
        self.assertEqual(len(effects), 1)
        self.assertEqual(evidence["status"], "unknown")
        self.assertEqual(persisted, "unknown")

    def test_f6_linear_reread_requires_observed_comment(self):
        issue = {"id": "synthetic-issue", "description": "unchanged", "url": "https://example.invalid/issue", "comments": {"nodes": []}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(pub, "RUNS_DIR", Path(tmp)), \
             patch.object(lp.linear_ad, "read_issue", return_value=issue), \
             patch.object(lp.linear_ad, "comment_create", return_value={
                 "comment": {"id": "synthetic-comment", "body": "finding"}, "issue": issue}):
            _, evidence = lp.publish_linear_comment(
                PublicationJournal(run_id="probe"),
                issue_id="synthetic-issue",
                body="finding",
            )
        self.assertFalse(evidence["reread"])
        self.assertNotEqual(evidence["status"], "published")

    def test_f7_linear_restart_does_not_duplicate_after_timeout(self):
        issue = {"id": "synthetic-issue", "description": "unchanged", "comments": {"nodes": []}}
        effects = []

        def create(*args, **kwargs):
            effects.append("synthetic-comment")
            raise TimeoutError("controlled timeout after fake comment commit")

        with tempfile.TemporaryDirectory() as tmp, patch.object(pub, "RUNS_DIR", Path(tmp)), \
             patch.object(lp.linear_ad, "read_issue", return_value=issue), \
             patch.object(lp.linear_ad, "comment_create", side_effect=create):
            for _ in range(2):
                lp.publish_linear_comment(pub.load_journal("probe"), issue_id="synthetic-issue", body="finding")
            status = pub.load_journal("probe").linear_comment_status
        self.assertEqual(len(effects), 1)
        self.assertEqual(status, "unknown")

    def test_f8_shared_session_rejects_content_only_mutant(self):
        from apps.notifier.notifier import ReleaseNotifier
        from apps.notifier.policies import RecoveryReport
        from invariant.harness import make_session
        from invariant.candidate_runner import evaluate_candidate_matrix

        original = ReleaseNotifier.announce
        seen = {}

        def content_dedupe(self, destination, operation_id, content, recovery=None):
            key = (id(self), destination, content)
            if key in seen:
                return RecoveryReport(0, True, False, False, None, None, "synthetic content-only mutant")
            seen[key] = True
            return original(self, destination, operation_id, content, recovery=recovery)

        source = gen.render_generated_tests(CONTRACT)
        with patch.object(ReleaseNotifier, "announce", content_dedupe):
            adapter, observer, _store = make_session()
            notifier = ReleaseNotifier(adapter)
            notifier.announce("C-RELEASES", "A", "identical")
            notifier.announce("C-RELEASES", "B", "identical")
            a = observer.count("C-RELEASES", "A", "identical")
            b = observer.count("C-RELEASES", "B", "identical")
        self.assertEqual((a, b), (1, 0))
        matrix = evaluate_candidate_matrix(source)
        self.assertTrue(matrix.ok, matrix.reason)
        mutant_run = next(item for item in matrix.runs if item.implementation == "content_dedup")
        self.assertTrue(mutant_run.ok_for_impl)
        self.assertTrue(any("legitimate_new_operation" in f for f in mutant_run.failures))


if __name__ == "__main__":
    unittest.main()
