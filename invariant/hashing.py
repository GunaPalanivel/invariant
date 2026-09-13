"""Content hashes for AUT revision and generated/handwritten tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def hash_paths(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda p: str(p).replace("\\", "/")):
        digest.update(str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def aut_revision_hash() -> str:
    notifier = ROOT / "apps" / "notifier"
    files = sorted(p for p in notifier.rglob("*.py") if p.is_file())
    return hash_paths(files)


def hash_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())
