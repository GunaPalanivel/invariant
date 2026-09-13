"""Live Slack/Linear publication with GET-before-write and reread."""

from __future__ import annotations

from invariant.adapters import linear as linear_ad
from invariant.adapters import slack as slack_ad
from invariant.hashing import sha256_text
from invariant.models import PublicationJournal
from invariant.publication import (
    PublicationBlocked,
    reconcile_before_write,
    save_journal,
    strip_fixture_slack_linear,
)


def _comment_nodes(issue: dict) -> list[dict]:
    comments = issue.get("comments") or {}
    if isinstance(comments, dict):
        return list(comments.get("nodes") or [])
    if isinstance(comments, list):
        return comments
    return []


def _issue_comment_url(issue: dict, comment_id: str | None) -> str | None:
    if not comment_id:
        return None
    base = str(issue.get("url") or "").rstrip("/")
    if not base:
        return None
    return f"{base}#comment-{comment_id}"


def publish_slack_finding(
    journal: PublicationJournal,
    *,
    channel: str,
    thread_ts: str,
    text: str,
    operation_id: str | None,
) -> tuple[PublicationJournal, dict]:
    journal = strip_fixture_slack_linear(journal)
    evidence: dict = {"url": None, "ts": None, "status": "deferred"}
    if not channel or not thread_ts:
        evidence["status"] = "blocked"
        evidence["error"] = "SLACK_TEST_CHANNEL_ID or SLACK_TEST_THREAD_TS missing"
        journal.slack_reply_status = "deferred"
        save_journal(journal)
        return journal, evidence
    try:
        action = reconcile_before_write(journal, "slack_reply_status", "slack_reply_ts")
    except PublicationBlocked as exc:
        journal.slack_reply_status = "unknown"
        save_journal(journal)
        return journal, {"url": None, "ts": journal.slack_reply_ts, "status": "unknown", "error": str(exc)}

    if action == "reuse" and journal.slack_reply_ts:
        reread = slack_ad.conversations_replies(channel, thread_ts)
        seen = any(m.get("ts") == journal.slack_reply_ts for m in reread.get("messages") or [])
        body_ok = True
        if journal.evidence_version:
            body_ok = any(
                journal.evidence_version in str(m.get("text") or "")
                for m in reread.get("messages") or []
                if m.get("ts") == journal.slack_reply_ts
            )
        url = slack_ad.chat_get_permalink(channel, journal.slack_reply_ts) or slack_ad.archive_url(
            channel, journal.slack_reply_ts
        )
        ok = seen and body_ok
        evidence = {
            "url": url if ok else None,
            "ts": journal.slack_reply_ts,
            "status": "published" if ok else "unknown",
            "reused": True,
            "reread": ok,
        }
        if not ok:
            journal.slack_reply_status = "unknown"
            save_journal(journal)
        return journal, evidence

    journal.slack_channel_id = channel
    journal.slack_thread_ts = thread_ts
    journal.slack_operation_id = operation_id
    journal.slack_payload_hash = sha256_text(text)
    journal.slack_reply_status = "pending"
    save_journal(journal)
    try:
        posted = slack_ad.chat_post_message(channel, text, thread_ts=thread_ts, operation_id=operation_id)
    except slack_ad.SlackError as exc:
        journal.slack_reply_status = "unknown"
        save_journal(journal)
        return journal, {
            "url": None,
            "ts": None,
            "status": "unknown",
            "error": str(exc),
            "reused": False,
            "reread": False,
        }
    if posted.get("_invariant_write_unknown"):
        journal.slack_reply_status = "unknown"
        save_journal(journal)
        return journal, {
            "url": None,
            "ts": None,
            "status": "unknown",
            "error": "chat.postMessage internal_error/fatal_error; no second reply",
        }
    ts = posted.get("ts")
    reread = slack_ad.conversations_replies(channel, thread_ts)
    seen = any(m.get("ts") == ts for m in reread.get("messages") or [])
    url = slack_ad.chat_get_permalink(channel, ts or "") or slack_ad.archive_url(channel, ts or "")
    journal.slack_reply_ts = ts
    journal.slack_reply_status = "published" if seen else "unknown"
    save_journal(journal)
    evidence = {
        "url": url if seen else None,
        "ts": ts,
        "status": journal.slack_reply_status,
        "reused": False,
        "reread": seen,
        "method": "chat.postMessage",
    }
    return journal, evidence


def publish_linear_comment(
    journal: PublicationJournal,
    *,
    issue_id: str,
    body: str,
) -> tuple[PublicationJournal, dict]:
    journal = strip_fixture_slack_linear(journal)
    evidence: dict = {"url": None, "comment_id": None, "status": "deferred", "description_preserved": None}
    if not issue_id:
        evidence["status"] = "blocked"
        evidence["error"] = "LINEAR_ISSUE_ID missing"
        journal.linear_comment_status = "deferred"
        save_journal(journal)
        return journal, evidence
    before = linear_ad.read_issue(issue_id)
    uuid = before.get("id") or issue_id
    description = before.get("description")
    try:
        action = reconcile_before_write(journal, "linear_comment_status", "linear_comment_id")
    except PublicationBlocked as exc:
        journal.linear_comment_status = "unknown"
        save_journal(journal)
        return journal, {**evidence, "status": "unknown", "error": str(exc), "reread": False}

    if action == "reuse" and journal.linear_comment_id:
        comments = _comment_nodes(before)
        seen = any(
            c.get("id") == journal.linear_comment_id
            and (not journal.evidence_version or journal.evidence_version in str(c.get("body") or ""))
            for c in comments
        )
        preserved = before.get("description") == description
        url = _issue_comment_url(before, journal.linear_comment_id)
        evidence = {
            "url": url if seen else None,
            "comment_id": journal.linear_comment_id,
            "issue_uuid": uuid,
            "status": "published" if seen else "unknown",
            "reused": True,
            "reread": seen,
            "description_preserved": preserved,
        }
        if not seen:
            journal.linear_comment_status = "unknown"
            save_journal(journal)
        return journal, evidence

    journal.linear_issue_id = uuid
    journal.linear_payload_hash = sha256_text(body)
    journal.linear_comment_status = "pending"
    save_journal(journal)
    try:
        created = linear_ad.comment_create(uuid, body)
    except Exception as exc:
        journal.linear_comment_status = "unknown"
        save_journal(journal)
        return journal, {
            **evidence,
            "status": "unknown",
            "error": f"{type(exc).__name__}: {exc}",
            "reread": False,
            "reused": False,
        }
    comment = created.get("comment") or {}
    reread = created.get("issue") or {}
    comment_id = comment.get("id")
    preserved = reread.get("description") == description
    seen = bool(
        comment_id
        and any(c.get("id") == comment_id and str(c.get("body") or "") == str(comment.get("body") or body) for c in _comment_nodes(reread))
    )
    journal.linear_comment_id = comment_id
    journal.linear_comment_status = "published" if (seen and preserved) else "unknown"
    save_journal(journal)
    evidence = {
        "url": _issue_comment_url(before if before.get("url") else reread, comment_id),
        "comment_id": comment_id,
        "issue_uuid": uuid,
        "issue_url": before.get("url") or reread.get("url"),
        "status": journal.linear_comment_status,
        "reused": False,
        "reread": seen,
        "description_preserved": preserved,
        "method": "commentCreate",
    }
    return journal, evidence
