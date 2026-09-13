"""Resumable publication journal. Local by default; live apps only with credentials."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from invariant.hashing import ROOT
from invariant.models import PublicationJournal

RUNS_DIR = ROOT / "runs"


class PublicationBlocked(RuntimeError):
    """Prior write is unknown; a second object must not be created."""


FIXTURE_SLACK_CHANNELS = {"C-RELEASES", "C-ADMIN"}
FIXTURE_LINEAR_ISSUES = {"INV-18"}


def journal_path(run_id: str) -> Path:
    return RUNS_DIR / run_id / "journal.json"


def load_journal(run_id: str) -> PublicationJournal:
    path = journal_path(run_id)
    if not path.exists():
        return PublicationJournal(run_id=run_id)
    return PublicationJournal.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_journal(journal: PublicationJournal) -> Path:
    path = journal_path(journal.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(journal.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def strip_fixture_slack_linear(journal: PublicationJournal) -> PublicationJournal:
    """Drop local-journal Slack/Linear ids so live writes are not treated as reuse."""
    channel = journal.slack_channel_id or ""
    thread = journal.slack_thread_ts or ""
    reply = journal.slack_reply_ts or ""
    if (
        channel in FIXTURE_SLACK_CHANNELS
        or thread.startswith("1726200000")
        or reply.endswith(".reply")
    ):
        journal.slack_channel_id = None
        journal.slack_thread_ts = None
        journal.slack_reply_ts = None
        journal.slack_reply_status = None
    issue = journal.linear_issue_id or ""
    comment = journal.linear_comment_id or ""
    if issue in FIXTURE_LINEAR_ISSUES or comment.startswith("comment-"):
        journal.linear_issue_id = None
        journal.linear_comment_id = None
        journal.linear_comment_status = None
    return journal


def _status(journal: PublicationJournal, field: str) -> str | None:
    return getattr(journal, field)


def reconcile_before_write(journal: PublicationJournal, status_field: str, id_field: str) -> str:
    """Return reuse | write | block."""
    status = _status(journal, status_field)
    existing = getattr(journal, id_field)
    if status == "unknown":
        raise PublicationBlocked(
            f"{status_field} is unknown; refusing a second write for run {journal.run_id}"
        )
    if status == "published" and existing:
        return "reuse"
    return "write"


class LocalAppStore:
    """File-backed stand-in for Slack/Linear/GitHub objects until live creds exist."""

    def __init__(self, run_id: str) -> None:
        self.root = RUNS_DIR / run_id / "local_apps"
        self.root.mkdir(parents=True, exist_ok=True)

    def _write(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = self.root / f"{name}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload

    def get(self, name: str) -> dict[str, Any] | None:
        path = self.root / f"{name}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def slack_reply(self, channel_id: str, thread_ts: str, text: str, reply_ts: str) -> dict[str, Any]:
        return self._write(
            "slack_reply",
            {
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "reply_ts": reply_ts,
                "text": text,
                "mode": "local_journal",
            },
        )

    def linear_comment(self, issue_id: str, body: str, comment_id: str) -> dict[str, Any]:
        issue_path = self.root / "linear_issue.json"
        if not issue_path.exists():
            self._write(
                "linear_issue",
                {"id": issue_id, "description": "ORIGINAL DESCRIPTION MUST BE PRESERVED", "comments": []},
            )
        issue = json.loads(issue_path.read_text(encoding="utf-8"))
        comments = list(issue.get("comments") or [])
        comments.append({"id": comment_id, "body": body})
        issue["comments"] = comments
        issue_path.write_text(json.dumps(issue, indent=2) + "\n", encoding="utf-8")
        return self._write("linear_comment", {"id": comment_id, "issue_id": issue_id, "body": body})

    def github_pr(self, branch: str, number: int, head_sha: str, body: str) -> dict[str, Any]:
        return self._write(
            "github_pr",
            {
                "number": number,
                "branch": branch,
                "head_sha": head_sha,
                "body": body,
                "mode": "local_journal",
                "ci_bound": False,
                "unbound_reason": "unbound — no hosted CI; local content hash only",
            },
        )


def publish_local(
    run_id: str,
    *,
    slack_channel_id: str,
    slack_thread_ts: str,
    linear_issue_id: str,
    github_branch: str,
    github_head_sha: str,
    summary: str,
    force_unknown: str | None = None,
) -> PublicationJournal:
    journal = load_journal(run_id)
    store = LocalAppStore(run_id)

    action = reconcile_before_write(journal, "slack_reply_status", "slack_reply_ts")
    if action == "write":
        reply_ts = f"{slack_thread_ts}.reply"
        if force_unknown == "slack":
            journal.slack_channel_id = slack_channel_id
            journal.slack_thread_ts = slack_thread_ts
            journal.slack_reply_status = "unknown"
            save_journal(journal)
        else:
            store.slack_reply(slack_channel_id, slack_thread_ts, summary, reply_ts)
            journal.slack_channel_id = slack_channel_id
            journal.slack_thread_ts = slack_thread_ts
            journal.slack_reply_ts = reply_ts
            journal.slack_reply_status = "published"
            save_journal(journal)

    action = reconcile_before_write(journal, "linear_comment_status", "linear_comment_id")
    if action == "write":
        comment_id = f"comment-{run_id}"
        store.linear_comment(linear_issue_id, summary, comment_id)
        journal.linear_issue_id = linear_issue_id
        journal.linear_comment_id = comment_id
        journal.linear_comment_status = "published"
        save_journal(journal)

    action = reconcile_before_write(journal, "github_pr_status", "github_pr_number")
    if action == "write":
        store.github_pr(github_branch, 1, github_head_sha, summary)
        journal.github_branch = github_branch
        journal.github_pr_number = 1
        journal.github_head_sha = github_head_sha
        journal.github_pr_status = "published"
        journal.ci_bound = False
        save_journal(journal)

    return load_journal(run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--channel", default="C-RELEASES")
    parser.add_argument("--thread", default="1726200000.000100")
    parser.add_argument("--linear", default="INV-18")
    parser.add_argument("--branch", default="invariant/regression-release-v42")
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--summary", default="Invariant local publication (injected transport).")
    args = parser.parse_args(argv)
    journal = publish_local(
        args.run_id,
        slack_channel_id=args.channel,
        slack_thread_ts=args.thread,
        linear_issue_id=args.linear,
        github_branch=args.branch,
        github_head_sha=args.head_sha,
        summary=args.summary,
    )
    print(json.dumps(journal.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
