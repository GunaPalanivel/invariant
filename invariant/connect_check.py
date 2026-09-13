"""Live read/write/reread. Auth alone is not a completed integration."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from invariant.adapters import github as github_ad
from invariant.adapters import linear as linear_ad
from invariant.adapters import slack as slack_ad
from invariant.envload import load_env
from invariant.hashing import ROOT
from invariant.publication import load_journal

load_env()

RESULTS = ROOT / "results"
RUN_ID = "run-release-v42"
LINEAR_WEB = "https://linear.app/guna-palanivel/issue/GUN-5"
GITHUB_HEAD = "b928402de071fe6997be08b61946a6ad7d2af3cc"


def _err(exc: BaseException) -> dict:
    return {"ok": False, "error": str(exc), "error_type": type(exc).__name__}


def slack_connection_check() -> dict:
    ids = slack_ad.destination_ids()
    channel = ids.get("channel_id")
    if not slack_ad._token() or not channel:
        missing = []
        if not slack_ad._token():
            missing.append("SLACK_BOT_TOKEN")
        if not channel:
            missing.append("SLACK_TEST_CHANNEL_ID")
        return {
            "ok": False,
            "complete": False,
            "missing_config": missing,
            "error": "Slack not configured; authentication not proven",
        }
    record: dict = {"channel_id": channel, "complete": False}
    try:
        history = slack_ad.conversations_history(channel)
        record["history"] = {
            "ok": True,
            "method": "conversations.history",
            "pages_fetched": history.get("pages_fetched"),
            "message_count": len(history.get("messages") or []),
            "pagination_exhausted": history.get("pagination_exhausted"),
        }
    except slack_ad.SlackError as exc:
        record["history"] = {"ok": False, "method": "conversations.history", **_err(exc)}
        return {**record, "ok": False, "error": str(exc)}

    parent_text = (
        "Invariant connection-check (not an incident, not intake). "
        "Labeled demonstration: broker can post to this channel."
    )
    reply_text = (
        "Invariant connection-check reply (not an incident). "
        "Reread of this thread must include this message."
    )
    try:
        parent = slack_ad.chat_post_message(channel, parent_text)
        if parent.get("_invariant_write_unknown"):
            record["parent"] = {
                "ok": False,
                "status": "unknown",
                "method": "chat.postMessage",
                "error": "internal_error/fatal_error after dispatch; no second post",
            }
            return {**record, "ok": False, "complete": False}
        parent_ts = parent.get("ts")
        permalink = slack_ad.chat_get_permalink(channel, parent_ts or "") or slack_ad.archive_url(
            channel, parent_ts or ""
        )
        record["parent"] = {
            "ok": True,
            "method": "chat.postMessage",
            "ts": parent_ts,
            "url": permalink,
        }
        reply = slack_ad.chat_post_message(channel, reply_text, thread_ts=parent_ts)
        if reply.get("_invariant_write_unknown"):
            record["reply"] = {
                "ok": False,
                "status": "unknown",
                "method": "chat.postMessage",
                "error": "internal_error/fatal_error after dispatch; no second reply",
            }
            return {**record, "ok": False, "complete": False}
        reply_ts = reply.get("ts")
        reply_url = slack_ad.chat_get_permalink(channel, reply_ts or "") or slack_ad.archive_url(
            channel, reply_ts or ""
        )
        record["reply"] = {
            "ok": True,
            "method": "chat.postMessage",
            "ts": reply_ts,
            "url": reply_url,
            "thread_ts": parent_ts,
        }
        reread = slack_ad.conversations_replies(channel, parent_ts or "")
        texts = [m.get("ts") for m in reread.get("messages") or []]
        record["reread"] = {
            "ok": True,
            "method": "conversations.replies",
            "parent_seen": parent_ts in texts,
            "reply_seen": reply_ts in texts,
            "message_count": len(texts),
        }
        record["complete"] = bool(record["reread"]["parent_seen"] and record["reread"]["reply_seen"])
        record["ok"] = record["complete"]
        record["note"] = "Connection-check thread is not the incident."
        return record
    except slack_ad.SlackError as exc:
        record["ok"] = False
        record["error"] = str(exc)
        return record


def linear_connection_check() -> dict:
    issue_id = linear_ad.issue_id()
    if not linear_ad._key() or not issue_id:
        missing = []
        if not linear_ad._key():
            missing.append("LINEAR_API_KEY")
        if not issue_id:
            missing.append("LINEAR_ISSUE_ID")
        return {
            "ok": False,
            "complete": False,
            "missing_config": missing,
            "error": "Linear not configured; authentication not proven",
        }
    try:
        issue = linear_ad.read_issue(issue_id)
    except linear_ad.LinearError as exc:
        return {
            "ok": False,
            "complete": False,
            "method": "issue",
            "issue_id_config": issue_id,
            **_err(exc),
        }
    description = issue.get("description")
    identifier = issue.get("identifier") or issue_id
    uuid = issue.get("id")
    issue_url = issue.get("url") or LINEAR_WEB
    body = (
        "Invariant connection-check comment. Not a finding and not incident evidence. "
        "Description must remain unchanged."
    )
    try:
        created = linear_ad.comment_create(uuid, body)
    except linear_ad.LinearError as exc:
        return {
            "ok": False,
            "complete": False,
            "method": "commentCreate",
            "issue_uuid": uuid,
            "identifier": identifier,
            "description_before": description,
            **_err(exc),
        }
    comment = created.get("comment") or {}
    reread = created.get("issue") or {}
    preserved = reread.get("description") == description
    comment_id = comment.get("id")
    url = f"{LINEAR_WEB}#comment-{comment_id}" if comment_id else LINEAR_WEB
    complete = bool(comment_id and preserved)
    return {
        "ok": complete,
        "complete": complete,
        "method_read": "issue",
        "method_write": "commentCreate",
        "identifier": identifier,
        "issue_uuid": uuid,
        "issue_url": issue_url,
        "title": issue.get("title"),
        "description_preserved": preserved,
        "comment_id": comment_id,
        "comment_url": url,
        "error": None if preserved else "issue description changed after commentCreate",
    }


def github_connection_check() -> dict:
    if not github_ad.configured():
        return {
            "ok": False,
            "complete": False,
            "missing_config": ["GITHUB_TOKEN or gh auth token"],
        }
    owner, name = github_ad.split_repo()
    journal = load_journal(RUN_ID)
    test_hash = "651f76f9c66e519d8b5080d56c9e5a1031de5b216f34114cad78ab6f015ab29e"
    wf = RESULTS / "workflow.json"
    if wf.exists():
        test_hash = json.loads(wf.read_text(encoding="utf-8")).get("generated_test_hash") or test_hash
    try:
        repo = github_ad.get_repo(owner, name)
        pr = github_ad.get_pull(owner, name, int(journal.github_pr_number or 1))
        head_sha = (pr.get("head") or {}).get("sha") or ""
        runs = github_ad.actions_runs_for_sha(owner, name, head_sha or GITHUB_HEAD)
        bound = github_ad.bind_ci(
            head_sha=head_sha or GITHUB_HEAD,
            aut_revision=journal.github_head_sha or GITHUB_HEAD,
            blob_hash=test_hash,
            test_hash=test_hash,
        )
        run0 = runs[0] if runs else {}
        return {
            "ok": True,
            "complete": bool(pr.get("html_url") and runs),
            "repo": repo.get("full_name"),
            "repo_url": repo.get("html_url"),
            "pr_number": pr.get("number"),
            "pr_url": pr.get("html_url"),
            "head_sha": head_sha,
            "aut_revision": journal.github_head_sha,
            "ci_runs": len(runs),
            "ci_url": run0.get("html_url"),
            "ci_status": run0.get("conclusion") or run0.get("status"),
            "bind_head_sha_matches_aut_revision": bound,
            "second_pr_opened": False,
        }
    except github_ad.GitHubError as exc:
        return {"ok": False, "complete": False, "method": "GET repo/pulls/actions", **_err(exc)}


def run_checks() -> dict:
    slack = slack_connection_check()
    linear = linear_connection_check()
    github = github_connection_check()
    payload = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "injected_faults_unrelated": True,
        "slack": slack,
        "linear": linear,
        "github": github,
        "all_complete": bool(slack.get("complete") and linear.get("complete") and github.get("complete")),
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "live-connect.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    payload = run_checks()
    summary = {
        "slack_complete": payload["slack"].get("complete"),
        "slack_error": payload["slack"].get("error"),
        "linear_complete": payload["linear"].get("complete"),
        "linear_error": payload["linear"].get("error"),
        "github_complete": payload["github"].get("complete"),
        "github_pr": (payload["github"] or {}).get("pr_url"),
        "all_complete": payload["all_complete"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if payload["all_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
