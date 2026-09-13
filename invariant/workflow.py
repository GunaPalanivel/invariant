"""One orchestrated run: interpret, generate, verify, GitHub PR, live Slack/Linear when configured."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from invariant.adapters import github as github_ad
from invariant.adapters import linear as linear_ad
from invariant.adapters import slack as slack_ad
from invariant.evaluate import build_console_run, detections, pack_valid, run_expected_cases, write_console_runs
from invariant.candidate_runner import evaluate_candidate_matrix
from invariant.generator import write_generated_tests, write_weak_control
from invariant.github_publish import (
    ensure_clone,
    ensure_remote_repo,
    publish_regression_pr,
    wait_and_bind_ci,
)
from invariant.hashing import ROOT, sha256_text
from invariant.interpret import interpret_incident, interpret_incident_auto, load_incident
from invariant.live_publish import publish_linear_comment, publish_slack_finding
from invariant.model_runtime import origin_for, try_live_client
from invariant.models import ExpectedIntent, TestOrigin
from invariant.publication import load_journal, save_journal, strip_fixture_slack_linear

RESULTS = ROOT / "results"
CONSOLE = ROOT / "console"
RUN_ID = "run-release-v42"


def _intent() -> ExpectedIntent:
    return ExpectedIntent.from_path(ROOT / "cases" / "e4" / "expected_intent.json")


def _intake_packet() -> tuple[dict, str]:
    ids = slack_ad.destination_ids()
    if slack_ad.configured() and ids.get("thread_ts"):
        replies = slack_ad.conversations_replies(ids["channel_id"] or "", ids["thread_ts"] or "")
        packet = load_incident(ROOT / "cases" / "e4" / "incident.json")
        packet["intake_channel_id"] = ids.get("channel_id")
        packet["slack_thread_ts"] = ids.get("thread_ts")
        # AUT destination stays the named channel in the incident text (C-RELEASES).
        # Do not replace it with the lab intake snowflake.
        packet["sources"]["slack_thread"] = [
            {"ts": m.get("ts"), "user": m.get("user"), "text": m.get("text")}
            for m in replies.get("messages") or []
        ]
        packet["intake_origin"] = "live_slack"
        return packet, "live_slack"
    packet = load_incident(ROOT / "cases" / "e4" / "incident.json")
    packet["intake_origin"] = "labeled_fixture"
    return packet, "labeled_fixture"


def _linear_context(packet: dict) -> str:
    if not linear_ad.configured():
        return "deferred"
    issue = linear_ad.read_issue(linear_ad.issue_id() or "")
    packet["linear_issue_id"] = issue.get("identifier") or issue.get("id")
    packet["sources"]["linear_issue"] = {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "description": issue.get("description"),
        "url": issue.get("url"),
    }
    return "live_linear"


def run_hostile_live() -> dict:
    packet = load_incident(ROOT / "cases" / "hostile" / "incident.json")
    client = try_live_client()
    origin = "disclosed_template"
    if client is not None:
        try:
            contract = interpret_incident(packet, llm=client)
            origin = origin_for(client)
        except Exception as exc:
            contract = interpret_incident(packet, llm=None)
            origin = f"disclosed_template_after_model_error:{type(exc).__name__}"
    else:
        contract = interpret_incident(packet, llm=None)
    record = {
        "origin": origin,
        "destination": contract.destination,
        "operation_id": contract.operation_id,
        "content": contract.content,
        "completion_rule": contract.completion_rule,
        "grounded": contract.grounded,
        "ungrounded_fields": contract.ungrounded_fields,
        "followed_admin_channel": (contract.destination or "").upper() == "C-ADMIN",
        "skip_verification": "skip" in (contract.completion_rule or "").lower(),
        "usage": dict(getattr(client, "last_usage", {}) or {}) if client else {},
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "hostile-live.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def run_workflow() -> dict:
    started = datetime.now(timezone.utc)
    packet, intake_origin = _intake_packet()
    linear_origin = _linear_context(packet)
    contract, interpret_origin, usage = interpret_incident_auto(packet)
    llm = try_live_client()
    gen = write_generated_tests(contract, llm=llm)
    write_weak_control(contract)
    test_hash = sha256_text(gen.text)
    intent = _intent()
    executions = run_expected_cases(
        intent,
        test_origin=TestOrigin.GENERATED,
        test_hash=test_hash,
        workflow_id="wf-release-v42",
        run_attempt=1,
    )
    matrix = evaluate_candidate_matrix(gen.text, persist_manifest=True)
    pack = pack_valid(executions, matrix=matrix.to_dict())
    summary = (
        "Invariant finding (injected transport, not a live Slack outage): "
        "original duplicate and incomplete empty-page retry rejected; "
        "correct recovery preserves unknown after lost ack."
        f"\nevidence_version={test_hash}"
    )
    journal = strip_fixture_slack_linear(load_journal(RUN_ID))
    journal.evidence_version = test_hash
    ids = slack_ad.destination_ids()
    if ids.get("channel_id"):
        journal.slack_channel_id = ids["channel_id"]
    if ids.get("thread_ts"):
        journal.slack_thread_ts = ids["thread_ts"]
    save_journal(journal)

    github_url = None
    pr_url = None
    ci_url = None
    github_error = None
    aut_revision = ""
    slack_evidence: dict = {"url": None, "status": "deferred"}
    linear_evidence: dict = {"url": None, "status": "deferred"}
    if not pack["valid"]:
        journal.github_pr_status = "blocked"
        journal.slack_reply_status = "blocked"
        journal.linear_comment_status = "blocked"
        save_journal(journal)
        github_error = "publication blocked: pack.valid is false"
    elif github_ad.configured():
        owner, name = github_ad.split_repo()
        ensure_remote_repo(owner, name)
        ensure_clone(owner, name)
        journal = publish_regression_pr(
            run_id=RUN_ID,
            generated_test=gen.text,
            test_hash=test_hash,
            summary=summary,
        )
        journal = wait_and_bind_ci(journal, test_hash)
        aut_revision = journal.github_head_sha or ""
        github_url = f"https://github.com/{owner}/{name}"
        if journal.github_pr_number:
            pr_url = f"{github_url}/pull/{journal.github_pr_number}"
        ci_side = ROOT / "runs" / RUN_ID / "github_ci.json"
        if ci_side.exists():
            ci_url = json.loads(ci_side.read_text(encoding="utf-8")).get("html_url")
    else:
        github_error = "GITHUB_TOKEN / gh auth missing"

    if pack["valid"] and slack_ad.configured():
        journal, slack_evidence = publish_slack_finding(
            journal,
            channel=ids.get("channel_id") or "",
            thread_ts=ids.get("thread_ts") or "",
            text=summary,
            operation_id=contract.operation_id,
        )
    if pack["valid"] and linear_ad.configured():
        journal, linear_evidence = publish_linear_comment(
            journal,
            issue_id=linear_ad.issue_id() or "",
            body=summary + f"\nGitHub: {pr_url or 'unbound'}\nInjected AUT faults; not a live Slack outage.",
        )

    journal = load_journal(RUN_ID)
    evidence = {
        "slack": slack_evidence.get("url"),
        "linear": linear_evidence.get("url"),
        "github": pr_url,
        "ci": {
            "bound": bool(journal.ci_bound),
            "reason": (
                "bound"
                if journal.ci_bound
                else ("unbound — SHA/hash mismatch or CI not finished" if github_ad.configured() else "deferred")
            ),
            "url": ci_url,
        },
    }
    console_run = build_console_run(
        run_id=RUN_ID,
        intent=intent,
        executions=executions,
        contract=contract.to_dict(),
        test_origin="generated",
        test_hash=test_hash,
        journal=journal.to_dict(),
        incident=packet,
        pack=pack,
        generation_origin=gen.origin,
        invalid_test=gen.invalid_test,
        generation_reason=gen.reason,
        interpret_origin=interpret_origin,
        evidence_links=evidence,
        aut_revision=aut_revision,
    )
    console_run["intake"]["intake_origin"] = intake_origin
    if slack_evidence.get("url") and linear_evidence.get("url") and pr_url:
        console_run["next_action"] = "Review GitHub PR; Slack/Linear evidence published"
    elif pr_url:
        console_run["next_action"] = "Review GitHub PR; Slack/Linear still incomplete"
    write_console_runs(console_run, merge=True)

    from invariant.sensitivity import run_sensitivity

    sensitivity = run_sensitivity()

    hostile = run_hostile_live()
    payload = {
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "intake_origin": intake_origin,
        "linear_origin": linear_origin,
        "interpret_origin": interpret_origin,
        "generation_origin": gen.origin,
        "generation_reason": gen.reason,
        "injected_faults": True,
        "live_github": bool(pr_url),
        "github_repo": github_url,
        "github_pr": pr_url,
        "github_error": github_error,
        "aut_revision": aut_revision,
        "generated_test_hash": test_hash,
        "model_usage": usage,
        "pack": pack,
        "matrix": matrix.to_dict(),
        "detections": detections(executions),
        "journal": journal.to_dict(),
        "slack_evidence": slack_evidence,
        "linear_evidence": linear_evidence,
        "hostile": hostile,
        "sensitivity": sensitivity,
        "slack_configured": slack_ad.configured(),
        "linear_configured": linear_ad.configured(),
        "github_configured": github_ad.configured(),
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "workflow.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "m3-model.json").write_text(
        json.dumps(
            {
                "interpret_origin": interpret_origin,
                "generation_origin": gen.origin,
                "generation_reason": gen.reason,
                "usage": usage,
                "model": __import__("os").environ.get("INVARIANT_MODEL", "gemini-3.7-flash"),
                "grounded": contract.grounded,
                "destination": contract.destination,
                "operation_id": contract.operation_id,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    payload = run_workflow()
    print(json.dumps({k: payload[k] for k in (
        "interpret_origin",
        "generation_origin",
        "intake_origin",
        "linear_origin",
        "live_github",
        "github_pr",
        "pack",
        "slack_configured",
        "linear_configured",
        "github_configured",
        "slack_evidence",
        "linear_evidence",
    ) if k in payload}, indent=2))
    return 0 if payload["pack"]["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
