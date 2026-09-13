"""Write an execution manifest for the generated test file this tree actually contains."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import unittest
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _test_path() -> Path:
    path = ROOT / "tests" / "test_generated_aut.py"
    if not path.exists():
        path = ROOT / "generated" / "test_generated_aut.py"
    return path


def _run_tests() -> dict:
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), pattern="test_*.py")
    stream = StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return {
        "tests_run": result.testsRun,
        "errors": [f"{test}" for test, _exc in result.errors],
        "failures": [f"{test}" for test, _exc in result.failures],
        "error_count": len(result.errors),
        "failure_count": len(result.failures),
        "ok": result.wasSuccessful(),
        "output": stream.getvalue(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-tests", action="store_true")
    args = parser.parse_args(argv)
    path = _test_path()
    raw = path.read_bytes() if path.exists() else b""
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    results = (
        _run_tests()
        if args.run_tests
        else {
            "tests_run": None,
            "errors": [],
            "failures": [],
            "error_count": None,
            "failure_count": None,
            "ok": None,
            "output": "",
        }
    )
    payload = {
        "workflow": os.environ.get("GITHUB_WORKFLOW") or "ci",
        "head_sha": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "executed_file": str(path.relative_to(ROOT)).replace("\\", "/") if path.exists() else None,
        "blob_hash": hashlib.sha256(normalized).hexdigest(),
        "bytes": len(normalized),
        "implementation": os.environ.get("INVARIANT_AUT_IMPLEMENTATION"),
        "tests_run": results["tests_run"],
        "errors": results["errors"],
        "failures": results["failures"],
        "error_count": results["error_count"],
        "failure_count": results["failure_count"],
        "ok": results["ok"],
    }
    (ROOT / "execution-manifest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(payload["blob_hash"])
    if args.run_tests and not results["ok"]:
        sys.stderr.write(results.get("output") or "")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
