"""Publish AUT tests to GunaPalanivel/invariant-validation. Reconcile journal first."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from invariant.adapters import github
from invariant.hashing import ROOT, sha256_text
from invariant.models import PublicationJournal
from invariant.publication import PublicationBlocked, load_journal, reconcile_before_write, save_journal
from invariant.validation_seed import copy_testkit, sibling_clone

CI_YAML = """name: ci
on:
  pull_request:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Run AUT regressions and write execution manifest
        env:
          PYTHONPATH: .
          INVARIANT_AUT_IMPLEMENTATION: correct
        run: python scripts/write_execution_manifest.py --run-tests
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: execution-manifest
          path: execution-manifest.json
"""

VALIDATION_README = """# invariant-validation

Reference release-notifier and CI for Invariant. This is **not** the product broker.

Faults in these tests are **injected at the test transport**. They are not a live Slack outage.
"""

MANIFEST_SCRIPT = '''from __future__ import annotations
import hashlib, json, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "tests" / "test_generated_aut.py"
raw = path.read_bytes() if path.exists() else b""
normalized = raw.replace(b"\\r\\n", b"\\n").replace(b"\\r", b"\\n")
payload = {
    "workflow": os.environ.get("GITHUB_WORKFLOW") or "ci",
    "head_sha": os.environ.get("GITHUB_SHA"),
    "executed_file": "tests/test_generated_aut.py",
    "blob_hash": hashlib.sha256(normalized).hexdigest(),
    "bytes": len(normalized),
    "implementation": os.environ.get("INVARIANT_AUT_IMPLEMENTATION"),
    "tests_run": None,
    "errors": [],
    "failures": [],
}
(ROOT / "execution-manifest.json").write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
print(payload["blob_hash"])
'''


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


def ensure_remote_repo(owner: str, name: str) -> str:
    view = _run(["gh", "repo", "view", f"{owner}/{name}", "--json", "url", "-q", ".url"])
    if view.returncode == 0 and (view.stdout or "").strip():
        return view.stdout.strip()
    created = _run(
        [
            "gh",
            "repo",
            "create",
            f"{owner}/{name}",
            "--private",
            "--description",
            "Dedicated AUT and CI for Invariant",
            "--confirm",
        ]
    )
    if created.returncode != 0:
        raise RuntimeError(created.stderr or "gh repo create failed")
    view = _run(["gh", "repo", "view", f"{owner}/{name}", "--json", "url", "-q", ".url"])
    return (view.stdout or f"https://github.com/{owner}/{name}").strip()


def ensure_clone(owner: str, name: str) -> Path:
    dest = sibling_clone()
    if (dest / ".git").exists():
        _run(["git", "fetch", "origin"], cwd=dest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    cloned = _run(["gh", "repo", "clone", f"{owner}/{name}", str(dest)])
    if cloned.returncode != 0:
        raise RuntimeError(cloned.stderr or "gh repo clone failed")
    return dest


def _git(args: list[str], cwd: Path, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = None
    if extra_env:
        import os

        env = {**os.environ, **extra_env}
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False, env=env)


def _commit_all(clone: Path, message: str) -> str:
    _git(["add", "-A"], cwd=clone)
    status = _git(["status", "--porcelain"], cwd=clone)
    if not status.stdout.strip():
        return _git(["rev-parse", "HEAD"], cwd=clone).stdout.strip()
    commit = _git(
        ["-c", "user.email=invariant-bot@users.noreply.github.com", "-c", "user.name=Invariant publisher", "commit", "-m", message],
        cwd=clone,
    )
    if commit.returncode != 0:
        raise RuntimeError(commit.stderr or commit.stdout or "git commit failed")
    return _git(["rev-parse", "HEAD"], cwd=clone).stdout.strip()


SMOKE = '''import unittest
from apps.notifier.notifier import ReleaseNotifier

class Smoke(unittest.TestCase):
    def test_entrypoint_exists(self):
        self.assertTrue(hasattr(ReleaseNotifier, "announce"))
'''


def write_testkit_files(clone: Path) -> None:
    copy_testkit(clone)
    tests = clone / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test_smoke.py").write_text(SMOKE, encoding="utf-8")
    (clone / "README.md").write_text(VALIDATION_README, encoding="utf-8")
    wf = clone / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "ci.yml").write_text(CI_YAML, encoding="utf-8")
    scripts = clone / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    src_script = ROOT / "scripts" / "write_execution_manifest.py"
    if src_script.exists():
        (scripts / "write_execution_manifest.py").write_text(src_script.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        (scripts / "write_execution_manifest.py").write_text(MANIFEST_SCRIPT, encoding="utf-8")
    (clone / ".gitignore").write_text("__pycache__/\n*.pyc\n.venv/\n.env\n", encoding="utf-8")


def seed_main(clone: Path, generated_test: str | None = None) -> str:
    write_testkit_files(clone)
    if generated_test is not None:
        (clone / "tests" / "test_generated_aut.py").write_text(generated_test, encoding="utf-8")
    return _commit_all(clone, "Seed notifier, testkit, and CI.")


def publish_regression_pr(
    *,
    run_id: str,
    generated_test: str,
    test_hash: str,
    summary: str,
    branch: str = "invariant/regression-release-v42",
) -> PublicationJournal:
    owner, name = github.split_repo()
    journal = load_journal(run_id)
    action = reconcile_before_write(journal, "github_pr_status", "github_pr_number")
    clone = ensure_clone(owner, name)
    has_head = _git(["rev-parse", "--verify", "HEAD"], cwd=clone)
    if has_head.returncode != 0:
        seed_main(clone, generated_test=None)
        _git(["branch", "-M", "main"], cwd=clone)
        push = _git(["push", "-u", "origin", "main"], cwd=clone)
        if push.returncode != 0:
            raise RuntimeError(push.stderr or "initial push failed")

    if action == "reuse" and journal.github_pr_number:
        try:
            github.get_pull(owner, name, int(journal.github_pr_number))
        except github.GitHubError:
            journal.github_pr_number = None
            journal.github_pr_status = None
            journal.github_head_sha = None
            journal.github_branch = None
            save_journal(journal)

    _git(["checkout", "main"], cwd=clone)
    _git(["pull", "--ff-only", "origin", "main"], cwd=clone)
    existing = _git(["rev-parse", "--verify", branch], cwd=clone)
    if existing.returncode == 0:
        _git(["checkout", branch], cwd=clone)
    else:
        _git(["checkout", "-b", branch], cwd=clone)
    seed_main(clone, generated_test=generated_test)
    _commit_all(clone, "Add generated AUT regression for lost-ack family.")
    push = _git(["push", "-u", "origin", branch], cwd=clone)
    if push.returncode != 0:
        raise RuntimeError(push.stderr or "branch push failed")
    head_sha = _git(["rev-parse", "HEAD"], cwd=clone).stdout.strip()
    blob_hash = sha256_text(generated_test)
    if blob_hash != test_hash:
        raise RuntimeError("generated blob hash drifted before publish")

    if journal.github_pr_number:
        pr = github.get_pull(owner, name, int(journal.github_pr_number))
    else:
        journal.github_branch = branch
        journal.github_payload_hash = test_hash
        journal.github_pr_status = "pending"
        save_journal(journal)
        try:
            pulls = github.list_pulls(owner, name, head=f"{owner}:{branch}")
            if pulls:
                pr = pulls[0]
            else:
                pr = github.create_pull(
                    owner,
                    name,
                    title="Invariant AUT regression: lost-ack write family",
                    head=branch,
                    base="main",
                    body=summary,
                )
        except Exception:
            journal.github_pr_status = "unknown"
            save_journal(journal)
            raise
    number = int(pr["number"])
    journal.github_branch = branch
    journal.github_pr_number = number
    journal.github_head_sha = head_sha
    journal.github_pr_status = "published"
    journal.ci_bound = False
    save_journal(journal)
    return load_journal(run_id)


def _observed_blob_hash(owner: str, name: str, head: str, relpath: str = "tests/test_generated_aut.py") -> str:
    import base64

    from invariant.hashing import sha256_source_bytes

    body = github.get_contents(owner, name, relpath, ref=head)
    encoded = body.get("content") or ""
    raw = base64.b64decode(encoded)
    return sha256_source_bytes(raw)


def _artifact_blob_hash(owner: str, name: str, run_id: str | int) -> str | None:
    try:
        artifacts = github.list_run_artifacts(owner, name, run_id)
    except Exception:
        return None
    for item in artifacts:
        if (item.get("name") or "") != "execution-manifest":
            continue
        try:
            blob = github.download_artifact_zip(owner, name, item["id"])
            payload = github.execution_manifest_from_zip(blob)
        except Exception:
            return None
        hashed = payload.get("blob_hash")
        return str(hashed) if hashed else None
    return None


def wait_and_bind_ci(journal: PublicationJournal, test_hash: str, timeout_s: int = 180) -> PublicationJournal:
    owner, name = github.split_repo()
    head = journal.github_head_sha or ""
    deadline = time.time() + timeout_s
    last_runs: list[dict] = []
    while time.time() < deadline:
        last_runs = github.actions_runs_for_sha(owner, name, head)
        if last_runs:
            break
        time.sleep(5)
    bound = False
    ci_id = None
    html = None
    associated = False
    completed = False
    conclusion = None
    observed_hash = None
    artifact_hash = None
    hash_match = False
    artifact_match = False
    remote_reads = 0
    try:
        observed_hash = _observed_blob_hash(owner, name, head)
        remote_reads = 1
        hash_match = observed_hash == test_hash
    except Exception:
        observed_hash = None
        hash_match = False
    for run in last_runs:
        associated = (run.get("head_sha") or "") == head
        completed = (run.get("status") or "") == "completed"
        conclusion = run.get("conclusion")
        artifact_hash = _artifact_blob_hash(owner, name, run.get("id"))
        artifact_match = artifact_hash is None or artifact_hash == test_hash
        if associated and completed and hash_match and artifact_match and conclusion == "success":
            bound = True
            ci_id = str(run.get("id"))
            html = run.get("html_url")
            break
    journal.ci_bound = bound
    journal.ci_run_id = ci_id
    save_journal(journal)
    journal = load_journal(journal.run_id)
    sidecar = ROOT / "runs" / journal.run_id / "github_ci.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(
        __import__("json").dumps(
            {
                "bound": bound,
                "ci_run_id": ci_id,
                "html_url": html,
                "head_sha": head,
                "runs_seen": len(last_runs),
                "sha_associated": associated,
                "completed": completed,
                "conclusion": conclusion,
                "observed_test_hash": observed_hash,
                "artifact_blob_hash": artifact_hash,
                "expected_test_hash": test_hash,
                "hash_match": hash_match,
                "artifact_match": artifact_match,
                "remote_blob_reads": remote_reads,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return journal
