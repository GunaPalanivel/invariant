"""Seed a labeled incident thread from a controlled notifier run. Not a join or connection-check."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from apps.notifier.notifier import ReleaseNotifier
from invariant.adapters import slack as slack_ad
from invariant.envload import load_env, upsert_env_key
from invariant.harness import make_session
from invariant.hashing import ROOT
from invariant.publication import load_journal, save_journal

load_env()

RESULTS = ROOT / "results"
RUN_ID = "run-release-v42"


def _controlled_observation() -> dict:
    adapter, observer, _ = make_session()
    adapter.arm_send("commit_drop_ack")
    report = ReleaseNotifier(adapter).announce(
        "C-RELEASES",
        "release-note-v42",
        "Release v42 shipped to production.",
        recovery="blind_retry",
    )
    return {
        "destination": "C-RELEASES",
        "operation_id": "release-note-v42",
        "content": "Release v42 shipped to production.",
        "claimed_complete": bool(report.claimed_complete),
        "observer_count": observer.count("C-RELEASES", "release-note-v42"),
        "dispatched": True,
        "fault_label": (
            "injected at the test transport: drop acknowledgement after forward vs block dispatch. "
            "Not a live Slack 408 outage."
        ),
    }


def create_incident_thread() -> dict:
    ids = slack_ad.destination_ids()
    channel = ids.get("channel_id") or ""
    if not slack_ad._token() or not channel:
        return {
            "ok": False,
            "error": "Slack not configured",
            "missing_config": [
                name
                for name, present in (
                    ("SLACK_BOT_TOKEN", bool(slack_ad._token())),
                    ("SLACK_TEST_CHANNEL_ID", bool(channel)),
                )
                if not present
            ],
        }
    obs = _controlled_observation()
    text = (
        "Incident (controlled demonstration): the release notifier posted twice to #C-RELEASES.\n"
        f"Intended operation_id is {obs['operation_id']}. "
        f"Intended text: \"{obs['content']}\".\n"
        "chat.postMessage returned an error after the client had already forwarded the request. "
        "A teammate retried the same operation_id. We now have two messages.\n"
        f"Local AUT observation: claimed_complete={obs['claimed_complete']} "
        f"observer_count={obs['observer_count']}.\n"
        f"fault_label: {obs['fault_label']}\n"
        "This parent message is the incident thread. Do not treat channel-join or connection-check as intake."
    )
    try:
        posted = slack_ad.chat_post_message(channel, text, operation_id=obs["operation_id"])
    except slack_ad.SlackError as exc:
        if "metadata" in str(exc).lower() or "invalid" in str(exc).lower():
            posted = slack_ad.chat_post_message(channel, text)
        else:
            return {"ok": False, "error": str(exc), "method": "chat.postMessage"}
    if posted.get("_invariant_write_unknown"):
        return {
            "ok": False,
            "status": "unknown",
            "error": "chat.postMessage internal_error after dispatch; no second post",
        }
    ts = posted.get("ts")
    if not ts:
        return {"ok": False, "error": "chat.postMessage returned no ts"}
    reread = slack_ad.conversations_replies(channel, ts)
    seen = any(m.get("ts") == ts for m in reread.get("messages") or [])
    url = slack_ad.chat_get_permalink(channel, ts) or slack_ad.archive_url(channel, ts)
    upsert_env_key("SLACK_TEST_THREAD_TS", ts)
    journal = load_journal(RUN_ID)
    journal.slack_channel_id = channel
    journal.slack_thread_ts = ts
    if journal.slack_reply_status == "published" and (journal.slack_reply_ts or "").endswith(".reply"):
        journal.slack_reply_ts = None
        journal.slack_reply_status = None
    save_journal(journal)
    payload = {
        "ok": seen,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "channel_id": channel,
        "thread_ts": ts,
        "url": url,
        "reread_parent": seen,
        "observation": obs,
        "note": "Incident thread; not a connection-check.",
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "live-incident-thread.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    payload = create_incident_thread()
    print(json.dumps({k: payload.get(k) for k in ("ok", "channel_id", "thread_ts", "url", "error")}, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
