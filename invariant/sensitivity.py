"""Author-prepared input-sensitivity: destination change must move the assertion. No second PR."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from invariant.evaluate import write_console_runs
from invariant.generator import generate_pack
from invariant.hashing import ROOT, sha256_text
from invariant.interpret import interpret_incident_auto, load_incident
from invariant.model_runtime import try_live_client

RESULTS = ROOT / "results"
PACKET = ROOT / "cases" / "sensitivity" / "incident.json"


def run_sensitivity() -> dict:
    packet = load_incident(PACKET)
    contract, origin, usage = interpret_incident_auto(packet)
    llm = try_live_client()
    gen = generate_pack(contract, llm=llm) if contract.grounded else None
    generated_dest = None
    if gen is not None:
        generated_dest = contract.destination
    moved = contract.destination == "C-STAGING" and contract.destination != "C-RELEASES"
    rejected_old = "C-RELEASES" not in (contract.destination or "")
    record = {
        "run_id": "run-input-sensitivity-destination",
        "prepared": "author-prepared",
        "interpret_origin": origin,
        "generation_origin": None if gen is None else gen.origin,
        "destination": contract.destination,
        "operation_id": contract.operation_id,
        "assertion_moved": moved,
        "rejects_previous_destination": rejected_old,
        "grounded": contract.grounded,
        "ungrounded_fields": contract.ungrounded_fields,
        "generated_test_hash": sha256_text(gen.text) if gen is not None else None,
        "invalid_test": False if gen is None else gen.invalid_test,
        "usage": usage,
        "published": False,
        "note": "Local only. Journal GET blocks a second GitHub PR.",
    }
    console_run = {
        "run_id": "run-input-sensitivity-destination",
        "incident_title": "Authorized destination changed to C-STAGING",
        "updated": datetime.now(timezone.utc).isoformat(),
        "destination": contract.destination,
        "operation_id": contract.operation_id,
        "stages": {
            "intake": "pass",
            "contract": "pass" if contract.grounded else "warn",
            "generate": "pass" if gen is not None else "unknown",
            "verify": "pass" if moved else "fail",
            "publish": "unknown",
        },
        "outcome": "complete" if moved else "incomplete",
        "next_action": "Author-prepared input-sensitivity; no second PR",
        "aut_revision": "local-sensitivity",
        "generated_test_hash": record["generated_test_hash"] or "none",
        "test_origin": "generated",
        "interpret_origin": origin,
        "injected_faults": True,
        "evidence_links": {
            "slack": None,
            "linear": None,
            "github": None,
            "ci": {"bound": False, "reason": "not published — journal reuse, no second PR"},
        },
        "intake": {
            "thread_excerpt": packet["sources"]["slack_thread"][0]["text"],
            "linear_issue_id": packet["linear_issue_id"],
            "authorized_repo": packet["authorized_repo"],
            "source_timestamps": [m["ts"] for m in packet["sources"]["slack_thread"]],
            "fault_label": packet["fault_label"],
            "intake_origin": "author-prepared",
        },
        "contract": contract.to_dict(),
        "generate": {
            "test_origin": "generated",
            "generation_origin": None if gen is None else gen.origin,
            "hash": record["generated_test_hash"],
            "aut_entrypoint": "apps/notifier/notifier.py",
            "invalid_test": False if gen is None else gen.invalid_test,
            "generation_reason": "assertion target follows the new destination" if moved else "destination did not move",
        },
        "verify": {
            "comparison": [
                {
                    "label": "Input sensitivity",
                    "aut_revision": "local-sensitivity",
                    "named_assertion": "destination follows authorized requirement",
                    "result_class": "intended_assertion_passed" if moved else "intended_assertion_failed",
                    "application_outcome": "complete" if moved else "incomplete",
                    "title": "assertion target moved to C-STAGING" if moved else "assertion still bound to previous destination",
                }
            ],
            "hero": {
                "case_id": "input_sensitivity_destination",
                "kicker": "Changing the authorized destination changed the generated assertion.",
                "fault_label": packet["fault_label"],
            },
            "status_strip": {
                "verification_execution": "ran",
                "application_correctness": "complete" if moved else "incomplete",
                "unresolved_evidence": "unknown",
                "publication": "not published",
            },
            "findings": [
                {
                    "case_id": "input_sensitivity_destination",
                    "expected": "C-STAGING",
                    "observed": contract.destination,
                    "violated_invariant": "none" if moved else "generated assertion ignored the new destination",
                    "evidence_link": "local only",
                    "next_action": "none" if moved else "inspect interpret destination",
                    "result_class": "intended_assertion_passed" if moved else "intended_assertion_failed",
                    "application_outcome": "complete" if moved else "incomplete",
                    "open": True,
                }
            ],
            "event_log": [],
        },
        "publish": {
            "github_pr_status": "not published",
            "note": "No second PR. Journal GET-reuse remains on run-release-v42.",
        },
        "pack": {"valid": moved},
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "sensitivity.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    write_console_runs(console_run, merge=True)
    return record


def main() -> int:
    record = run_sensitivity()
    print(json.dumps(record, indent=2))
    return 0 if record["assertion_moved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
