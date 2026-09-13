"""Copy AUT + testkit into the sibling validation clone. Never copies the broker."""

from __future__ import annotations

import shutil
from pathlib import Path

from invariant.hashing import ROOT

PRODUCT_WHITELIST = [
    "apps/__init__.py",
    "apps/notifier/__init__.py",
    "apps/notifier/adapter.py",
    "apps/notifier/policies.py",
    "apps/notifier/notifier.py",
    "invariant/__init__.py",
    "invariant/hashing.py",
    "invariant/models.py",
    "invariant/observer.py",
    "invariant/harness.py",
    "invariant/assertions.py",
    "invariant/verification.py",
]

BROKER_MUST_NOT_APPEAR = (
    "interpret.py",
    "generator.py",
    "publication.py",
    "workflow.py",
    "llm.py",
    "compare.py",
    "evaluate.py",
)


def sibling_clone() -> Path:
    return ROOT.parent / "invariant-validation"


def copy_testkit(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for rel in PRODUCT_WHITELIST:
        src = ROOT / rel
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    # Slim package init: no env/model load in the AUT repo.
    (dest / "invariant" / "__init__.py").write_text(
        '"""Testkit subset for invariant-validation. No broker, no scoring keys."""\n__version__ = "0.1.0"\n',
        encoding="utf-8",
    )
    for name in BROKER_MUST_NOT_APPEAR:
        leftover = dest / "invariant" / name
        if leftover.exists():
            leftover.unlink()
