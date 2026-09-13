"""AUT must not see hidden world labels or ExpectedIntent."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FORBIDDEN_NAMES = {"World", "COMMITTED", "NOT_COMMITTED", "VALID_ORDINARY", "ExpectedIntent"}


def names_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in FORBIDDEN_NAMES:
                found.add(node.value)
    return found


class TestHiddenWorld(unittest.TestCase):
    def test_notifier_package_has_no_world_labels(self):
        for path in (ROOT / "apps" / "notifier").rglob("*.py"):
            found = names_in(path) & FORBIDDEN_NAMES
            self.assertEqual(found, set(), msg=str(path))

    def test_policies_do_not_take_world_argument(self):
        source = (ROOT / "apps" / "notifier" / "policies.py").read_text(encoding="utf-8")
        self.assertNotIn("world", source)
