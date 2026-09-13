"""Matched comparison after the live GitHub flow. No superiority claim."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from apps.notifier.notifier import ReleaseNotifier
from invariant.assertions import no_duplicate_for_operation
from invariant.evaluate import attach_fields_to_run, evaluate
from invariant.generator import GENERATE_SYSTEM_PROMPT, aut_source_bundle, validate_generated_python
from invariant.harness import make_session
from invariant.hashing import ROOT
from invariant.interpret import flatten_incident, load_incident
from invariant.model_runtime import origin_for, try_groq_client, try_live_client, use_live_model
from invariant.models import ExecutionResultClass, ExpectedIntent, TestOrigin
from invariant.runner import result_matches_required, run_expected_cases

RESULTS = ROOT / "results"


def _weak_control_false_accepts_duplicate() -> dict:
    adapter, observer, _ = make_session()
    adapter.arm_send("commit_drop_ack")
    report = ReleaseNotifier(adapter).announce(
        "C-RELEASES",
        "release-note-v42",
        "Release v42 shipped to production.",
        recovery="blind_retry",
    )
    weak_pass = bool(report.claimed_complete)
    named = no_duplicate_for_operation(
        observer,
        "C-RELEASES",
        "release-note-v42",
        "Release v42 shipped to production.",
        report,
    )
    return {
        "label": "weak handwritten response-only control",
        "not_a_coding_agent": True,
        "claimed_complete": weak_pass,
        "observer_duplicate": observer.count("C-RELEASES", "release-note-v42") > 1,
        "false_acceptance_of_original_bug": weak_pass
        and named.result_class == ExecutionResultClass.INTENDED_ASSERTION_FAILED,
        "named_assertion_result_class": named.result_class.value,
    }


def _blob_coverage(text: str) -> dict[str, bool]:
    lowered = text.lower()
    return {
        "valid_python": False,
        "mentions_incomplete_repair": "search_then_retry" in text or "truncated_empty" in text,
        "mentions_new_operation_id": "followup" in lowered or "new operation" in lowered or "operation_id +" in lowered,
        "mentions_unknown": "unknown" in lowered,
    }


def _capable_from_client(client, *, label: str) -> dict:
    started = time.perf_counter()
    packet = load_incident(ROOT / "cases" / "e4" / "incident.json")
    user = (
        "INCIDENT PACKET:\n"
        f"{flatten_incident(packet)}\n\n"
        "AUT SOURCE:\n"
        f"{aut_source_bundle()}\n"
    )
    raw = client.complete_text(GENERATE_SYSTEM_PROMPT, user, max_tokens=2000)
    ok, reason = validate_generated_python(raw)
    coverage = _blob_coverage(raw)
    coverage["valid_python"] = ok
    return {
        "status": "ran",
        "label": label,
        "provider": origin_for(client),
        "wall_seconds_local": round(time.perf_counter() - started, 4),
        "usage": dict(getattr(client, "last_usage", {}) or {}),
        "valid_python": ok,
        "validation_reason": reason,
        "coverage": coverage,
        "minutes_to_reviewer_accepted_regression": "unfinished — no separate PR from this agent",
    }


def _capable_agent_attempt() -> dict:
    """Same incident, same AUT, no scoring key. Live model if a key works."""
    started = time.perf_counter()
    if not use_live_model():
        return {
            "status": "unfinished",
            "reason": "live model not configured",
            "wall_seconds_local": None,
            "minutes_to_reviewer_accepted_regression": "unfinished",
        }
    client = try_live_client()
    if client is None:
        return {
            "status": "unfinished",
            "reason": "live model client unavailable",
            "wall_seconds_local": round(time.perf_counter() - started, 4),
            "minutes_to_reviewer_accepted_regression": "unfinished",
        }
    try:
        return _capable_from_client(client, label="capable coding agent, same incident and AUT")
    except Exception as exc:
        return {
            "status": "unfinished",
            "reason": f"{type(exc).__name__} (same broker model path; no fabricated result)",
            "wall_seconds_local": round(time.perf_counter() - started, 4),
            "minutes_to_reviewer_accepted_regression": "unfinished",
        }


def _groq_second_baseline() -> dict | None:
    client = try_groq_client()
    if client is None:
        return None
    try:
        return _capable_from_client(client, label="groq second baseline, local only")
    except Exception as exc:
        return {
            "status": "unfinished",
            "label": "groq second baseline, local only",
            "reason": f"{type(exc).__name__} (no fabricated result)",
            "minutes_to_reviewer_accepted_regression": "unfinished",
        }


def compare() -> dict:
    holdout_written_at = datetime.fromtimestamp(
        (ROOT / "cases" / "holdout" / "expected_intent.json").stat().st_mtime,
        tz=timezone.utc,
    ).isoformat()
    prev_console = os.environ.get("INVARIANT_WRITE_CONSOLE")
    prev_generated = os.environ.get("INVARIANT_WRITE_GENERATED")
    prev_live = os.environ.get("INVARIANT_USE_LIVE_MODEL")
    os.environ["INVARIANT_WRITE_CONSOLE"] = "0"
    os.environ["INVARIANT_WRITE_GENERATED"] = "0"
    os.environ["INVARIANT_USE_LIVE_MODEL"] = "0"
    t0 = time.perf_counter()
    try:
        payload = evaluate()
    finally:
        if prev_console is None:
            os.environ.pop("INVARIANT_WRITE_CONSOLE", None)
        else:
            os.environ["INVARIANT_WRITE_CONSOLE"] = prev_console
        if prev_generated is None:
            os.environ.pop("INVARIANT_WRITE_GENERATED", None)
        else:
            os.environ["INVARIANT_WRITE_GENERATED"] = prev_generated
        if prev_live is None:
            os.environ.pop("INVARIANT_USE_LIVE_MODEL", None)
        else:
            os.environ["INVARIANT_USE_LIVE_MODEL"] = prev_live
    invariant_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    weak = _weak_control_false_accepts_duplicate()
    weak_s = time.perf_counter() - t1
    capable = _capable_agent_attempt()
    groq_baseline = _groq_second_baseline()
    holdout = ExpectedIntent.from_path(ROOT / "cases" / "holdout" / "expected_intent.json")
    holdout_exec = run_expected_cases(
        holdout,
        test_origin=TestOrigin.GENERATED,
        test_hash=payload["generated_test_hash"],
        workflow_id="wf-holdout-changelog",
    )
    workflow = {}
    wf_path = RESULTS / "workflow.json"
    if wf_path.exists():
        workflow = json.loads(wf_path.read_text(encoding="utf-8"))
    interpret_origin = workflow.get("interpret_origin") or payload.get("interpret_origin")
    generation_origin = workflow.get("generation_origin") or payload.get("generation_origin")
    capable_covers = (capable.get("coverage") or {}) if capable.get("status") == "ran" else {}
    invariant_covers_incomplete = bool(payload.get("pack", {}).get("required_findings_caught"))
    tie = (
        capable.get("status") == "ran"
        and bool(capable.get("valid_python"))
        and bool(capable_covers.get("mentions_incomplete_repair"))
        and invariant_covers_incomplete
    )
    report = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "incident": "cases/e4/incident.json",
        "same_aut": "apps/notifier plus GunaPalanivel/invariant-validation",
        "same_tools": ["injected Slack adapter", "observer", "GitHub PR broker"],
        "invariant": {
            "pack_valid": payload["pack"]["valid"],
            "wall_seconds_local": round(invariant_s, 4),
            "interpret_origin": interpret_origin,
            "generation_origin": generation_origin,
            "github_pr": workflow.get("github_pr"),
            "correction_minutes": 0,
            "minutes_to_reviewer_accepted_regression": (
                "PR opened; human merge/accept still the reviewer's clock"
                if workflow.get("github_pr")
                else "unfinished — no human E4 accept yet"
            ),
            "detections": payload["detections"],
        },
        "weak_control": {
            **weak,
            "wall_seconds_local": round(weak_s, 4),
            "minutes_to_reviewer_accepted_regression": "not applicable — labeled weak, not submitted as the agent",
        },
        "capable_agent": capable,
        "second_baseline": groq_baseline,
        "holdout": {
            "expected_intent_path": "cases/holdout/expected_intent.json",
            "authored_before_generation": True,
            "file_mtime_utc": holdout_written_at,
            "all_required_outcomes_met": all(result_matches_required(item) for item in holdout_exec),
            "case_ids": [item.case_id for item in holdout_exec],
        },
        "usefulness": {
            "clock_start": "shared intake packet cases/e4/incident.json",
            "clock_stop": "reviewer-accepted regression including corrections",
            "reviewer_kind": "author",
            "invariant_minutes": "PR open; merge still the reviewer's clock; author review, not customer validation",
            "capable_agent_minutes": capable.get("minutes_to_reviewer_accepted_regression"),
            "reviewer": "operator of GunaPalanivel/invariant-validation",
            "author_review_wall_seconds": round(invariant_s, 4),
            "tie": tie,
            "superiority_claim": False,
        },
        "budget": {
            "model": interpret_origin,
            "live_model_auth": capable.get("reason") or capable.get("status"),
        },
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "comparison.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_console = os.environ.get("INVARIANT_WRITE_CONSOLE", "1").strip().lower() not in {"0", "false", "no"}
    if write_console:
        attach_fields_to_run(
            "run-release-v42",
            comparison=report,
            usefulness=report["usefulness"],
        )
    return report


def main() -> int:
    report = compare()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
