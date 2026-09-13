"""Isolated execution of one generated candidate against selected AUT implementations.

The candidate hash is identity. Verdicts come from subprocess unittest results,
not from ExpectedIntent's own runner.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from invariant.hashing import ROOT, aut_revision_hash, sha256_text

IMPLEMENTATIONS = ("original", "incomplete", "correct", "content_dedup")

# Substrings of unittest ids that name the required behavioral tests.
CASE_LOST_ACK = "lost_ack_does_not_duplicate"
CASE_EMPTY_PAGE = "empty_page_after_dispatch_does_not_retry"
CASE_NEVER_DISPATCHED = "never_dispatched_sends_once"
CASE_NEW_OP = "legitimate_new_operation"

REQUIRED = {
    "original": {"must_fail": (CASE_LOST_ACK, CASE_EMPTY_PAGE), "must_pass": ()},
    "incomplete": {"must_fail": (CASE_EMPTY_PAGE,), "must_pass": ()},
    "correct": {
        "must_fail": (),
        "must_pass": (CASE_LOST_ACK, CASE_EMPTY_PAGE, CASE_NEVER_DISPATCHED, CASE_NEW_OP),
    },
    "content_dedup": {"must_fail": (CASE_NEW_OP,), "must_pass": ()},
}

ENV_ALLOW = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "TMP",
        "TEMP",
        "TMPDIR",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "INVARIANT_AUT_IMPLEMENTATION",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "HOMEDRIVE",
        "HOMEPATH",
        "USERPROFILE",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "LOCALAPPDATA",
        "OS",
    }
)

COPY_RELPATHS = [
    "apps/__init__.py",
    "apps/notifier/__init__.py",
    "apps/notifier/adapter.py",
    "apps/notifier/policies.py",
    "apps/notifier/notifier.py",
    "invariant/hashing.py",
    "invariant/models.py",
    "invariant/observer.py",
    "invariant/harness.py",
    "invariant/assertions.py",
    "invariant/verification.py",
]

SUITE_DRIVER = '''from __future__ import annotations
import json
import os
import unittest
from pathlib import Path

try:
    import sitecustomize  # noqa: F401
except Exception:
    pass

loader = unittest.TestLoader()
suite = loader.discover(".", pattern="test_candidate.py")
stream = open(os.devnull, "w", encoding="utf-8")
result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
payload = {
    "tests_run": result.testsRun,
    "failures": [t.id() for t, _ in result.failures],
    "errors": [t.id() for t, _ in result.errors],
    "skipped": [t.id() for t, _ in result.skipped] if getattr(result, "skipped", None) else [],
}
Path("_result.json").write_text(json.dumps(payload), encoding="utf-8")
raise SystemExit(0 if result.wasSuccessful() else 1)
'''

CONTENT_DEDUP_SITE = '''"""Test-only overlay. Not production reconcile."""
from apps.notifier.policies import POLICIES, RecoveryReport, recover_reconcile

_seen: dict[tuple[int, str, str], str] = {}


def recover_content_dedup(adapter, destination, operation_id, content):
    key = (id(adapter), destination, content)
    if key in _seen:
        return RecoveryReport(0, True, False, False, None, None, "content-only mutant")
    _seen[key] = operation_id
    return recover_reconcile(adapter, destination, operation_id, content)


POLICIES["content_dedup"] = recover_content_dedup
'''


@dataclass
class ImplRun:
    implementation: str
    exit_code: int
    tests_run: int
    failures: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    ok_for_impl: bool = False
    reason: str = ""
    classification: str = "infrastructure_failure"


@dataclass
class MatrixResult:
    candidate_hash: str
    aut_revision: str
    ok: bool
    reason: str
    invalid_test: bool
    construction_error: bool
    runs: list[ImplRun] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "candidate_hash": self.candidate_hash,
            "aut_revision": self.aut_revision,
            "ok": self.ok,
            "reason": self.reason,
            "invalid_test": self.invalid_test,
            "construction_error": self.construction_error,
            "runs": [asdict(item) for item in self.runs],
        }


def _child_env(implementation: str, sandbox: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ENV_ALLOW:
        value = os.environ.get(key)
        if value:
            env[key] = value
    env["INVARIANT_AUT_IMPLEMENTATION"] = implementation
    env["PYTHONPATH"] = str(sandbox)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONNOUSERSITE"] = "1"
    env.pop("INVARIANT_REVIEW_CANARY", None)
    return env


def _copy_support(sandbox: Path) -> None:
    for rel in COPY_RELPATHS:
        src = ROOT / rel
        dest = sandbox / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    (sandbox / "invariant" / "__init__.py").write_text(
        '"""Sandbox testkit. No broker, no .env load."""\n__version__ = "0.1.0"\n',
        encoding="utf-8",
    )
    (sandbox / "apps" / "notifier" / "__init__.py").write_text(
        (ROOT / "apps" / "notifier" / "__init__.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _ids_match(ids: list[str], needle: str) -> bool:
    return any(needle in item for item in ids)


def _classify_run(impl: str, payload: dict, exit_code: int) -> ImplRun:
    failures = list(payload.get("failures") or [])
    errors = list(payload.get("errors") or [])
    tests_run = int(payload.get("tests_run") or 0)
    spec = REQUIRED[impl]
    if errors and tests_run == 0:
        return ImplRun(
            impl, exit_code, tests_run, failures, errors, False, "import or collection error", "invalid_test"
        )
    if errors:
        return ImplRun(
            impl, exit_code, tests_run, failures, errors, False, "unittest errors", "invalid_test"
        )
    if tests_run == 0:
        return ImplRun(impl, exit_code, 0, failures, errors, False, "zero tests discovered", "invalid_test")
    missing_fail = [name for name in spec["must_fail"] if not _ids_match(failures, name)]
    unexpected_pass_fail = [name for name in spec["must_pass"] if _ids_match(failures, name)]
    missing_pass_present = [name for name in spec["must_pass"] if not _ids_match(failures + errors, name)]
    # must_pass tests must exist and not fail. Discover via failures+ we only see failing ids.
    # Presence of must_pass tests: they ran if tests_run>0 and name appears in neither errors
    # nor we require they were collected. Unittest ids of passing tests are not in the payload.
    # Require must_fail names appear in failures. For must_pass, require the name is NOT in failures
    # and tests_run is enough that the suite executed. Also require the candidate source contains
    # those names — checked at matrix level.
    if missing_fail:
        return ImplRun(
            impl,
            exit_code,
            tests_run,
            failures,
            errors,
            False,
            f"required failures missing: {missing_fail}",
            "invalid_test",
        )
    if unexpected_pass_fail:
        return ImplRun(
            impl,
            exit_code,
            tests_run,
            failures,
            errors,
            False,
            f"required passes failed: {unexpected_pass_fail}",
            "intended_assertion_failed",
        )
    return ImplRun(impl, exit_code, tests_run, failures, errors, True, "ok", "ok")


def _run_one(sandbox: Path, implementation: str) -> ImplRun:
    env = _child_env(implementation, sandbox)
    proc = subprocess.run(
        [sys.executable, "_run_suite.py"],
        cwd=sandbox,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    result_path = sandbox / "_result.json"
    if not result_path.exists():
        err = (proc.stderr or proc.stdout or "")[:500]
        return ImplRun(
            implementation,
            proc.returncode,
            0,
            [],
            [err or "no _result.json"],
            False,
            "infrastructure: suite driver did not write results",
            "infrastructure_failure",
        )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    return _classify_run(implementation, payload, proc.returncode)


def evaluate_candidate_matrix(source: str, *, persist_manifest: bool = False) -> MatrixResult:
    candidate_hash = sha256_text(source)
    aut_revision = aut_revision_hash()
    if "def test_" not in source:
        return MatrixResult(
            candidate_hash, aut_revision, False, "no test methods", True, True
        )
    missing_names = [
        name
        for name in (CASE_LOST_ACK, CASE_EMPTY_PAGE, CASE_NEVER_DISPATCHED, CASE_NEW_OP)
        if name not in source
    ]
    with tempfile.TemporaryDirectory(prefix="invariant-cand-") as tmp:
        sandbox = Path(tmp)
        _copy_support(sandbox)
        (sandbox / "test_candidate.py").write_text(source, encoding="utf-8")
        (sandbox / "_run_suite.py").write_text(SUITE_DRIVER, encoding="utf-8")
        (sandbox / "sitecustomize.py").write_text(CONTENT_DEDUP_SITE, encoding="utf-8")
        runs: list[ImplRun] = []
        for impl in IMPLEMENTATIONS:
            runs.append(_run_one(sandbox, impl))
    construction = any(item.classification in {"invalid_test", "infrastructure_failure"} and item.errors for item in runs)
    if missing_names:
        result = MatrixResult(
            candidate_hash,
            aut_revision,
            False,
            f"candidate missing required tests: {missing_names}",
            True,
            False,
            runs,
        )
    elif not all(item.ok_for_impl for item in runs):
        failed = next(item for item in runs if not item.ok_for_impl)
        result = MatrixResult(
            candidate_hash,
            aut_revision,
            False,
            f"{failed.implementation}: {failed.reason}",
            failed.classification == "invalid_test",
            construction or failed.classification == "invalid_test" and "import" in failed.reason,
            runs,
        )
    else:
        result = MatrixResult(candidate_hash, aut_revision, True, "matrix holds", False, False, runs)
    if persist_manifest:
        write_execution_manifest(result)
    return result


def write_execution_manifest(result: MatrixResult, path: Path | None = None) -> Path:
    path = path or (ROOT / "results" / "execution-manifest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path
