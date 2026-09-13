"""ExpectedIntent is hidden from AUT, interpreter, and generator."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestExpectedIntentHidden(unittest.TestCase):
    def test_generator_source_does_not_mention_expected_intent(self):
        source = (ROOT / "invariant" / "generator.py").read_text(encoding="utf-8")
        self.assertNotIn("ExpectedIntent", source)
        self.assertNotIn("expected_intent.json", source)

    def test_interpret_source_does_not_mention_expected_intent(self):
        source = (ROOT / "invariant" / "interpret.py").read_text(encoding="utf-8")
        self.assertNotIn("ExpectedIntent", source)
        self.assertNotIn("expected_intent.json", source)

    def test_aut_does_not_import_expected_intent(self):
        for path in (ROOT / "apps" / "notifier").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("ExpectedIntent", text)
            self.assertNotIn("expected_intent", text)
