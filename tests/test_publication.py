"""Publication journal resume: unknown prior write blocks a second object."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invariant.publication import (
    LocalAppStore,
    PublicationBlocked,
    load_journal,
    publish_local,
    reconcile_before_write,
    save_journal,
)
from invariant.models import PublicationJournal
from invariant import publication as publication_mod


class TestPublicationJournal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        publication_mod.RUNS_DIR = Path(self.tmp.name)

    def test_first_publish_writes_local_objects(self):
        journal = publish_local(
            "run-a",
            slack_channel_id="C-RELEASES",
            slack_thread_ts="1.1",
            linear_issue_id="INV-18",
            github_branch="invariant/test",
            github_head_sha="abc",
            summary="finding",
        )
        self.assertEqual(journal.slack_reply_status, "published")
        self.assertEqual(journal.linear_comment_status, "published")
        self.assertEqual(journal.github_pr_status, "published")
        store = LocalAppStore("run-a")
        issue = json.loads((store.root / "linear_issue.json").read_text(encoding="utf-8"))
        self.assertEqual(issue["description"], "ORIGINAL DESCRIPTION MUST BE PRESERVED")
        self.assertEqual(len(issue["comments"]), 1)

    def test_resume_reuses_ids(self):
        first = publish_local(
            "run-b",
            slack_channel_id="C-RELEASES",
            slack_thread_ts="1.1",
            linear_issue_id="INV-18",
            github_branch="invariant/test",
            github_head_sha="abc",
            summary="finding",
        )
        second = publish_local(
            "run-b",
            slack_channel_id="C-RELEASES",
            slack_thread_ts="1.1",
            linear_issue_id="INV-18",
            github_branch="invariant/test",
            github_head_sha="abc",
            summary="finding again",
        )
        self.assertEqual(first.slack_reply_ts, second.slack_reply_ts)
        self.assertEqual(first.linear_comment_id, second.linear_comment_id)
        self.assertEqual(first.github_pr_number, second.github_pr_number)
        store = LocalAppStore("run-b")
        issue = json.loads((store.root / "linear_issue.json").read_text(encoding="utf-8"))
        self.assertEqual(len(issue["comments"]), 1)

    def test_unknown_prior_write_blocks_second(self):
        first = publish_local(
            "run-c",
            slack_channel_id="C-RELEASES",
            slack_thread_ts="1.1",
            linear_issue_id="INV-18",
            github_branch="invariant/test",
            github_head_sha="abc",
            summary="finding",
            force_unknown="slack",
        )
        self.assertEqual(first.slack_reply_status, "unknown")
        with self.assertRaises(PublicationBlocked):
            publish_local(
                "run-c",
                slack_channel_id="C-RELEASES",
                slack_thread_ts="1.1",
                linear_issue_id="INV-18",
                github_branch="invariant/test",
                github_head_sha="abc",
                summary="finding again",
            )

    def test_strip_fixture_keeps_github(self):
        journal = PublicationJournal(
            run_id="run-x",
            slack_channel_id="C-RELEASES",
            slack_thread_ts="1726200000.000100",
            slack_reply_ts="1726200000.000100.reply",
            slack_reply_status="published",
            linear_issue_id="INV-18",
            linear_comment_id="comment-run-x",
            linear_comment_status="published",
            github_pr_number=1,
            github_head_sha="abc",
            github_pr_status="published",
            ci_bound=True,
        )
        stripped = publication_mod.strip_fixture_slack_linear(journal)
        self.assertIsNone(stripped.slack_reply_ts)
        self.assertIsNone(stripped.linear_comment_id)
        self.assertEqual(stripped.github_pr_number, 1)
        self.assertTrue(stripped.ci_bound)

    def test_reconcile_unknown(self):
        journal = PublicationJournal(run_id="x", slack_reply_status="unknown")
        with self.assertRaises(PublicationBlocked):
            reconcile_before_write(journal, "slack_reply_status", "slack_reply_ts")
