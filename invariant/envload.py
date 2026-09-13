"""Load local .env without printing values. Called from broker entrypoints."""

from __future__ import annotations

from pathlib import Path

from invariant.hashing import ROOT


def load_env(root: Path | None = None) -> None:
    path = (root or ROOT) / ".env"
    try:
        from dotenv import load_dotenv
    except ImportError:
        _load_simple(path)
        return
    load_dotenv(path, override=False)


def upsert_env_key(key: str, value: str, root: Path | None = None) -> None:
    """Write one key into `.env` without printing values. Used for incident thread_ts."""
    import os

    path = (root or ROOT) / ".env"
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    found = False
    out: list[str] = []
    prefix = f"{key}="
    for line in lines:
        if line.startswith(prefix) or line.startswith(f"{key} ="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.environ[key] = value


def _load_simple(path: Path) -> None:
    import os

    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value
