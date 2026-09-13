"""Run the isolated original/incomplete/correct/mutant matrix and fail if it does not hold."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invariant.candidate_runner import evaluate_candidate_matrix
from invariant.hashing import sha256_source_bytes


def _test_path() -> Path:
    override = os.environ.get("INVARIANT_CANDIDATE_PATH")
    if override:
        return Path(override)
    path = ROOT / "tests" / "test_generated_aut.py"
    if not path.exists():
        path = ROOT / "generated" / "test_generated_aut.py"
    return path


def main() -> int:
    path = _test_path()
    if not path.exists():
        print("missing generated test file", file=sys.stderr)
        return 1
    source = path.read_text(encoding="utf-8")
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    result = evaluate_candidate_matrix(source, persist_manifest=False)
    payload = result.to_dict()
    executed = str(path.resolve().relative_to(ROOT)).replace("\\", "/") if path.resolve().is_relative_to(ROOT) else str(path)
    payload.update(
        {
            "workflow": os.environ.get("GITHUB_WORKFLOW") or "ci",
            "head_sha": os.environ.get("GITHUB_SHA"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "executed_file": executed,
            "blob_hash": sha256_source_bytes(raw),
            "bytes": len(raw),
        }
    )
    out = ROOT / "execution-manifest.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(payload["candidate_hash"])
    print(result.reason)
    if not result.ok:
        print(json.dumps({"ok": False, "reason": result.reason, "runs": payload.get("runs")}, indent=2), file=sys.stderr)
        return 1
    if payload["blob_hash"] != payload["candidate_hash"]:
        print("blob_hash drifted from candidate_hash", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
