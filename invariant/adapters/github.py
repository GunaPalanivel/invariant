"""GitHub REST broker. API version 2026-03-10. Bind CI only on matching head_sha."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from invariant.envload import load_env

load_env()

GITHUB_API = "https://api.github.com"
API_VERSION = os.environ.get("GITHUB_API_VERSION", "2026-03-10")
DEFAULT_REPO = "GunaPalanivel/invariant-validation"


class GitHubError(RuntimeError):
    pass


def _token() -> str | None:
    load_env()
    direct = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if direct:
        return direct
    try:
        proc = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        token = (proc.stdout or "").strip()
        if proc.returncode == 0 and token:
            return token
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def configured() -> bool:
    return bool(_token())


def repo_slug() -> str:
    load_env()
    return os.environ.get("GITHUB_REPO") or DEFAULT_REPO


def split_repo(slug: str | None = None) -> tuple[str, str]:
    slug = slug or repo_slug()
    owner, _, name = slug.partition("/")
    if not owner or not name:
        raise GitHubError("GITHUB_REPO must be owner/name")
    return owner, name


def _headers() -> dict[str, str]:
    token = _token()
    if not token:
        raise GitHubError("GITHUB_TOKEN is not set; live GitHub is deferred")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "invariant-hackathon",
    }


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    url = GITHUB_API + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GitHubError(f"HTTP {exc.code} {method} {path}: {detail[:800]}") from exc


def get_repo(owner: str, repo: str) -> dict[str, Any]:
    return _request("GET", f"/repos/{owner}/{repo}")


def get_ref(owner: str, repo: str, ref: str) -> dict[str, Any]:
    return _request("GET", f"/repos/{owner}/{repo}/git/ref/{ref}")


def create_ref(owner: str, repo: str, ref: str, sha: str) -> dict[str, Any]:
    return _request("POST", f"/repos/{owner}/{repo}/git/refs", {"ref": ref, "sha": sha})


def update_ref(owner: str, repo: str, ref: str, sha: str, *, force: bool = False) -> dict[str, Any]:
    return _request(
        "PATCH",
        f"/repos/{owner}/{repo}/git/refs/{ref}",
        {"sha": sha, "force": force},
    )


def get_commit(owner: str, repo: str, sha: str) -> dict[str, Any]:
    return _request("GET", f"/repos/{owner}/{repo}/git/commits/{sha}")


def create_blob(owner: str, repo: str, content: str) -> str:
    body = _request(
        "POST",
        f"/repos/{owner}/{repo}/git/blobs",
        {"content": content, "encoding": "utf-8"},
    )
    return str(body["sha"])


def create_tree(owner: str, repo: str, base_tree: str, entries: list[dict[str, Any]]) -> str:
    body = _request(
        "POST",
        f"/repos/{owner}/{repo}/git/trees",
        {"base_tree": base_tree, "tree": entries},
    )
    return str(body["sha"])


def create_commit(owner: str, repo: str, message: str, tree: str, parents: list[str]) -> str:
    body = _request(
        "POST",
        f"/repos/{owner}/{repo}/git/commits",
        {"message": message, "tree": tree, "parents": parents},
    )
    return str(body["sha"])


def put_contents(
    owner: str,
    repo: str,
    path: str,
    content: str,
    message: str,
    *,
    branch: str,
    sha: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    return _request("PUT", f"/repos/{owner}/{repo}/contents/{path}", payload)


def get_contents(owner: str, repo: str, path: str, ref: str | None = None) -> dict[str, Any]:
    suffix = f"?ref={urllib.parse.quote(ref)}" if ref else ""
    return _request("GET", f"/repos/{owner}/{repo}/contents/{path}{suffix}")


def create_pull(owner: str, repo: str, *, title: str, head: str, base: str, body: str) -> dict[str, Any]:
    return _request(
        "POST",
        f"/repos/{owner}/{repo}/pulls",
        {"title": title, "head": head, "base": base, "body": body},
    )


def list_pulls(owner: str, repo: str, *, head: str, state: str = "open") -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({"head": head, "state": state})
    body = _request("GET", f"/repos/{owner}/{repo}/pulls?{q}")
    return list(body) if isinstance(body, list) else []


def get_pull(owner: str, repo: str, number: int) -> dict[str, Any]:
    return _request("GET", f"/repos/{owner}/{repo}/pulls/{number}")


def actions_runs_for_sha(owner: str, repo: str, head_sha: str) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({"head_sha": head_sha})
    body = _request("GET", f"/repos/{owner}/{repo}/actions/runs?{q}")
    return list(body.get("workflow_runs") or [])


def list_run_artifacts(owner: str, repo: str, run_id: str | int) -> list[dict[str, Any]]:
    body = _request("GET", f"/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts")
    return list(body.get("artifacts") or [])


def download_artifact_zip(owner: str, repo: str, artifact_id: str | int) -> bytes:
    url = GITHUB_API + f"/repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GitHubError(f"HTTP {exc.code} GET artifact zip: {detail[:800]}") from exc


def execution_manifest_from_zip(blob: bytes) -> dict[str, Any]:
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = [name for name in archive.namelist() if name.endswith("execution-manifest.json")]
        if not names:
            return {}
        return json.loads(archive.read(names[0]).decode("utf-8"))


def bind_ci(*, head_sha: str, aut_revision: str, blob_hash: str, test_hash: str) -> bool:
    from invariant.verification import ci_may_inherit

    return ci_may_inherit(
        head_sha=head_sha, aut_revision=aut_revision, blob_hash=blob_hash, test_hash=test_hash
    )
