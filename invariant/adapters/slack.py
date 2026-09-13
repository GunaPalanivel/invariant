"""Slack broker for incident intake and thread replies.

Live calls require SLACK_BOT_TOKEN and dedicated test resources.
Generated tests never receive this token.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SLACK_API = "https://slack.com/api"
METADATA_EVENT_TYPE = "invariant_operation"


class SlackError(RuntimeError):
    pass


from invariant.envload import load_env

load_env()


def _token() -> str | None:
    load_env()
    return os.environ.get("SLACK_BOT_TOKEN") or os.environ.get("SLACK_TOKEN")


def configured() -> bool:
    return bool(_token() and os.environ.get("SLACK_TEST_CHANNEL_ID"))


def destination_ids() -> dict[str, str | None]:
    load_env()
    return {
        "channel_id": os.environ.get("SLACK_TEST_CHANNEL_ID"),
        "thread_ts": os.environ.get("SLACK_TEST_THREAD_TS"),
    }


def _call(method: str, payload: dict[str, Any] | None = None, params: dict[str, str] | None = None) -> dict[str, Any]:
    token = _token()
    if not token:
        raise SlackError("SLACK_BOT_TOKEN is not set; live Slack is deferred")
    url = f"{SLACK_API}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload else "GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SlackError(f"HTTP {exc.code} from Slack {method}") from exc
    if body.get("error") in {"internal_error", "fatal_error"}:
        body["_invariant_write_unknown"] = True
        return body
    if not body.get("ok"):
        err = body.get("error") or "unknown"
        needed = body.get("needed")
        hint = ""
        if err == "missing_scope":
            hint = f" required_scope={needed or 'chat:write|channels:history|groups:history'}"
        elif err == "not_in_channel":
            hint = " invite the bot into the channel"
        raise SlackError(f"{method} failed: {err}{hint}")
    return body


def conversations_replies(channel: str, ts: str) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    cursor = None
    while True:
        params = {"channel": channel, "ts": ts, "limit": "200", "include_all_metadata": "true"}
        if cursor:
            params["cursor"] = cursor
        body = _call("conversations.replies", params=params)
        if not body.get("ok"):
            raise SlackError(body.get("error") or "conversations.replies failed")
        messages.extend(body.get("messages") or [])
        meta = body.get("response_metadata") or {}
        cursor = meta.get("next_cursor") or None
        if not body.get("has_more") and not cursor:
            break
    return {"ok": True, "messages": messages, "pagination_exhausted": True}


def chat_post_message(
    channel: str,
    text: str,
    *,
    thread_ts: str | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    if operation_id:
        payload["metadata"] = {
            "event_type": METADATA_EVENT_TYPE,
            "event_payload": {"operation_id": operation_id},
        }
    return _call("chat.postMessage", payload=payload)


def chat_get_permalink(channel: str, message_ts: str) -> str | None:
    try:
        body = _call("chat.getPermalink", params={"channel": channel, "message_ts": message_ts})
    except SlackError:
        return None
    return body.get("permalink")


def archive_url(channel: str, ts: str) -> str:
    compact = (ts or "").replace(".", "")
    return f"https://invariantlab.slack.com/archives/{channel}/p{compact}"


def conversations_history(channel: str, *, oldest: str | None = None) -> dict[str, Any]:
    """Paginated history. Empty first page is not absence."""
    messages: list[dict[str, Any]] = []
    cursor = None
    pages = 0
    while True:
        params = {"channel": channel, "include_all_metadata": "true", "limit": "200"}
        if oldest:
            params["oldest"] = oldest
        if cursor:
            params["cursor"] = cursor
        body = _call("conversations.history", params=params)
        if not body.get("ok"):
            raise SlackError(body.get("error") or "conversations.history failed")
        pages += 1
        messages.extend(body.get("messages") or [])
        meta = body.get("response_metadata") or {}
        cursor = meta.get("next_cursor") or None
        has_more = bool(body.get("has_more") or cursor)
        if not has_more:
            break
    return {
        "ok": True,
        "messages": messages,
        "pages_fetched": pages,
        "has_more": False,
        "pagination_exhausted": True,
    }
