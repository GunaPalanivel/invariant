"""Evaluate AUT-bound cases. Console reads these records; it does not vote."""

from __future__ import annotations

import ast
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from invariant.access import write_report as write_access
from invariant.generator import write_generated_tests, write_weak_control
from invariant.hashing import ROOT, aut_revision_hash, sha256_text
from invariant.interpret import interpret_incident_auto, load_incident
from invariant.model_runtime import try_live_client
from invariant.models import (
    ExecutionResultClass,
    ExpectedIntent,
    TestOrigin,
)
from invariant.publication import publish_local
from invariant.runner import CaseExecution, result_matches_required, run_expected_cases

RESULTS = ROOT / "results"
CONSOLE = ROOT / "console"


def _load_intent() -> ExpectedIntent:
    return ExpectedIntent.from_path(ROOT / "cases" / "e4" / "expected_intent.json")


def _scan_forbidden_imports(root: Path, forbidden: tuple[str, ...]) -> list[str]:
    hits = []
    paths = [root] if root.is_file() else list(root.rglob("*.py"))
    for path in paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name.startswith(name) for name in forbidden):
                        hits.append(f"{path}:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module.startswith(name) for name in forbidden):
                    hits.append(f"{path}:{node.module}")
                for alias in node.names:
                    if alias.name in forbidden:
                        hits.append(f"{path}:{alias.name}")
        for name in forbidden:
            if name in source and name in ("ExpectedIntent",):
                hits.append(f"{path}:source:{name}")
    return hits


def detections(executions: list[CaseExecution]) -> dict[str, int]:
    counts = {cls.value: 0 for cls in ExecutionResultClass}
    for item in executions:
        counts[item.verification.result_class.value] += 1
    return counts


def pack_valid(executions: list[CaseExecution]) -> dict:
    """C5: every required named fault must fail independently (and, not any)."""
    by_id = {item.case_id: item for item in executions}
    required_findings = [
        "original_blind_retry_committed",
        "blanket_stop_never_dispatched",
        "incomplete_search_then_retry_degraded",
    ]
    required_passes = [
        "correct_committed",
        "correct_never_dispatched",
        "correct_legitimate_new_op",
        "correct_unknown_degraded_committed",
    ]
    finding_ok = all(
        by_id[name].verification.result_class == ExecutionResultClass.INTENDED_ASSERTION_FAILED
        for name in required_findings
    )
    pass_ok = all(
        by_id[name].verification.result_class == ExecutionResultClass.INTENDED_ASSERTION_PASSED
        for name in required_passes
    )
    unknown_ok = (
        by_id["correct_unknown_degraded_committed"].assertion.application_outcome.value
        == "unknown"
    )
    matches = all(result_matches_required(item) for item in executions)
    return {
        "valid": finding_ok and pass_ok and unknown_ok and matches,
        "required_findings_caught": finding_ok,
        "required_passes_ok": pass_ok,
        "unknown_not_painted_complete": unknown_ok,
        "matches_expected_intent": matches,
    }


def execution_to_dict(item: CaseExecution) -> dict:
    return {
        "case_id": item.case_id,
        "note": item.report_note,
        "assertion": {
            "named_assertion": item.assertion.named_assertion,
            "passed": item.assertion.passed,
            "expected": item.assertion.expected,
            "observed": item.assertion.observed,
            "violated_invariant": item.assertion.violated_invariant,
            "next_action": item.assertion.next_action,
            "result_class": item.assertion.result_class.value,
            "application_outcome": item.assertion.application_outcome.value,
        },
        "outcome": item.outcome.to_dict(),
        "verification": item.verification.to_dict(),
    }


def build_console_run(
    *,
    run_id: str,
    intent: ExpectedIntent,
    executions: list[CaseExecution],
    contract: dict,
    test_origin: str,
    test_hash: str,
    journal: dict,
    incident: dict,
    pack: dict,
    generation_origin: str = "disclosed_template",
    invalid_test: bool = False,
    generation_reason: str = "",
    interpret_origin: str = "disclosed_template",
    evidence_links: dict | None = None,
    aut_revision: str | None = None,
) -> dict:
    by_id = {item.case_id: item for item in executions}

    def cell(case_id: str, label: str) -> dict:
        item = by_id[case_id]
        return {
            "label": label,
            "aut_revision": item.verification.aut_revision,
            "named_assertion": item.assertion.named_assertion,
            "result_class": item.verification.result_class.value,
            "application_outcome": item.assertion.application_outcome.value,
            "title": (
                "application defect"
                if item.verification.result_class == ExecutionResultClass.INTENDED_ASSERTION_FAILED
                else "application recovered"
            ),
        }

    return {
        "run_id": run_id,
        "incident_title": "Release note posted twice after lost acknowledgement",
        "updated": datetime.now(timezone.utc).isoformat(),
        "destination": intent.destination,
        "operation_id": intent.operation_id,
        "stages": {
            "intake": "pass",
            "contract": "pass" if contract.get("grounded") else "warn",
            "generate": "pass",
            "verify": "pass" if pack["valid"] else "fail",
            "publish": journal.get("github_pr_status")
            or journal.get("slack_reply_status")
            or "unknown",
        },
        "outcome": "incomplete",
        "next_action": (
            "Review GitHub PR; Slack/Linear still deferred"
            if (evidence_links or {}).get("github")
            else "Live GitHub/Slack/Linear blocked until credentials; local journal persisted"
        ),
        "aut_revision": aut_revision or aut_revision_hash(),
        "generated_test_hash": test_hash,
        "test_origin": test_origin,
        "interpret_origin": interpret_origin,
        "injected_faults": True,
        "evidence_links": evidence_links
        or {
            "slack": None,
            "linear": None,
            "github": None,
            "ci": {"bound": False, "reason": "unbound — no hosted CI; local content hash only"},
        },
        "intake": {
            "thread_excerpt": incident["sources"]["slack_thread"][0]["text"],
            "linear_issue_id": incident["linear_issue_id"],
            "authorized_repo": incident["authorized_repo"],
            "source_timestamps": [m["ts"] for m in incident["sources"]["slack_thread"]],
            "fault_label": incident["fault_label"],
        },
        "contract": contract,
        "generate": {
            "test_origin": test_origin,
            "generation_origin": generation_origin,
            "hash": test_hash,
            "aut_entrypoint": "apps/notifier/notifier.py",
            "invalid_test": invalid_test,
            "generation_reason": generation_reason,
        },
        "verify": {
            "comparison": [
                cell("incomplete_search_then_retry_degraded", "Incomplete repair"),
                cell("original_blind_retry_committed", "Original bug"),
                cell("correct_committed", "Correct repair"),
            ],
            "hero": {
                "case_id": "incomplete_search_then_retry_degraded",
                "kicker": "Ordinary tests stayed green. This assertion still fails.",
                "fault_label": incident.get("fault_label") or "",
            },
            "status_strip": {
                "verification_execution": "ran",
                "application_correctness": "incomplete",
                "unresolved_evidence": "unknown",
                "publication": journal.get("github_pr_status") or "pending",
            },
            "findings": [
                {
                    "case_id": item.case_id,
                    "expected": item.assertion.expected,
                    "observed": item.assertion.observed,
                    "violated_invariant": item.assertion.violated_invariant or "none",
                    "evidence_link": "unbound — SHA mismatch / no hosted CI",
                    "next_action": item.assertion.next_action,
                    "result_class": item.verification.result_class.value,
                    "application_outcome": item.assertion.application_outcome.value,
                    "open": item.case_id == "incomplete_search_then_retry_degraded",
                }
                for item in sorted(
                    executions,
                    key=lambda item: 0 if item.case_id == "incomplete_search_then_retry_degraded" else 1,
                )
            ],
            "event_log": [
                {
                    "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                    "owner": "harness",
                    "message": f"{item.case_id}: {item.verification.result_class.value}",
                }
                for item in executions
            ],
        },
        "publish": journal,
        "pack": pack,
    }


def write_console_runs(*runs: dict, merge: bool = True) -> dict:
    CONSOLE.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    path = CONSOLE / "runs.json"
    if merge and path.exists():
        try:
            for item in json.loads(path.read_text(encoding="utf-8")).get("runs") or []:
                if item.get("run_id"):
                    existing[item["run_id"]] = item
        except json.JSONDecodeError:
            existing = {}
    for run in runs:
        existing[run["run_id"]] = run
    ordered: list[dict] = []
    if "run-release-v42" in existing:
        ordered.append(existing.pop("run-release-v42"))
    ordered.extend(existing.values())
    doc = {"runs": ordered}
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    (CONSOLE / "runs-data.js").write_text("window.INVARIANT_RUNS = " + json.dumps(doc) + ";\n", encoding="utf-8")
    return doc


def attach_fields_to_run(run_id: str, **fields: object) -> dict:
    path = CONSOLE / "runs.json"
    if not path.exists():
        return {"runs": []}
    doc = json.loads(path.read_text(encoding="utf-8"))
    for run in doc.get("runs") or []:
        if run.get("run_id") == run_id:
            run.update(fields)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    (CONSOLE / "runs-data.js").write_text("window.INVARIANT_RUNS = " + json.dumps(doc) + ";\n", encoding="utf-8")
    return doc


def evaluate() -> dict:
    write_access()
    intent = _load_intent()
    incident = load_incident(ROOT / "cases" / "e4" / "incident.json")
    contract, interpret_origin, model_usage = interpret_incident_auto(incident)
    llm = try_live_client()
    gen = write_generated_tests(contract, llm=llm)
    write_weak_control(contract)
    generated_text = gen.text
    generated_path = gen.path
    test_hash = sha256_text(generated_text)
    handwritten_hash = sha256_text(
        (ROOT / "handwritten" / "test_ambiguous_write.py").read_text(encoding="utf-8")
    )
    executions = run_expected_cases(
        intent,
        test_origin=TestOrigin.GENERATED,
        test_hash=test_hash,
        workflow_id="wf-release-v42",
        run_attempt=1,
    )
    pack = pack_valid(executions)
    aut_rev = aut_revision_hash()
    run_id = "run-release-v42"
    journal = publish_local(
        run_id,
        slack_channel_id=incident["slack_channel_id"],
        slack_thread_ts=incident["slack_thread_ts"],
        linear_issue_id=incident["linear_issue_id"],
        github_branch="invariant/regression-release-v42",
        github_head_sha=aut_rev,
        summary=(
            "Invariant finding (injected transport): original duplicate and incomplete "
            "empty-page retry rejected; correct recovery preserves unknown after lost ack."
        ),
    )
    console_run = build_console_run(
        run_id=run_id,
        intent=intent,
        executions=executions,
        contract=contract.to_dict(),
        test_origin="generated",
        test_hash=test_hash,
        journal=journal.to_dict(),
        incident=incident,
        pack=pack,
        generation_origin=gen.origin,
        invalid_test=gen.invalid_test,
        generation_reason=gen.reason,
        interpret_origin=interpret_origin,
    )
    holdout_intent = ExpectedIntent.from_path(ROOT / "cases" / "holdout" / "expected_intent.json")
    holdout = run_expected_cases(
        holdout_intent,
        test_origin=TestOrigin.GENERATED,
        test_hash=test_hash,
        workflow_id="wf-holdout-changelog",
        run_attempt=1,
    )
    payload = {
        "simulated": True,
        "injected_faults": True,
        "live_apps": False,
        "interpret_origin": interpret_origin,
        "generation_origin": gen.origin,
        "generation_reason": gen.reason,
        "model_usage": model_usage,
        "aut_revision": aut_rev,
        "generated_test_path": str(generated_path),
        "generated_test_hash": test_hash,
        "handwritten_test_hash": handwritten_hash,
        "detections": detections(executions),
        "pack": pack,
        "cases": [execution_to_dict(item) for item in executions],
        "holdout_cases": [execution_to_dict(item) for item in holdout],
        "forbidden_aut_imports": _scan_forbidden_imports(
            ROOT / "apps" / "notifier",
            ("invariant.models", "ExpectedIntent", "invariant.observer", "invariant.harness"),
        ),
        "forbidden_generator_imports": _scan_forbidden_imports(
            ROOT / "invariant" / "generator.py",
            ("cases.e4", "ExpectedIntent"),
        ),
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "evaluate.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_console = os.environ.get("INVARIANT_WRITE_CONSOLE", "1").strip().lower() not in {"0", "false", "no"}
    if write_console:
        write_console_runs(console_run, merge=True)
    return payload


def format_report(payload: dict) -> str:
    lines = [
        "INVARIANT EVALUATION — injected transport, not live Slack",
        "=" * 72,
        f"AUT revision: {payload['aut_revision']}",
        f"Generated test hash: {payload['generated_test_hash']}",
        f"Valid pack: {payload['pack']['valid']}",
        f"Result classes: {payload['detections']}",
        "",
    ]
    for case in payload["cases"]:
        ver = case["verification"]
        lines.append(
            f"  [{case['case_id']}] {ver['result_class']} "
            f"outcome={case['assertion']['application_outcome']} — {case['assertion']['observed']}"
        )
    lines.append("")
    lines.append("Live three-app publication: deferred (see results/m0-access.json)")
    return "\n".join(lines)


def main() -> int:
    payload = evaluate()
    print(format_report(payload))
    return 0 if payload["pack"]["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
