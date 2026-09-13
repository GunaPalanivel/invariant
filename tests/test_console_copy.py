"""Console copy and layout contracts."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONSOLE = ROOT / "console"
FORBIDDEN = (
    "Deccan",
    "g.palanivel@experts.crossinghurdles.com",
    "min-w-[1000px]",
    "min-width: 1000px",
    "ExpectedIntent",
    "ZIP package",
    "What to fix",
    "Stage 0",
)


class TestConsoleCopy(unittest.TestCase):
    def _all_text(self) -> str:
        parts = []
        for path in CONSOLE.iterdir():
            if path.suffix in {".html", ".css", ".js"}:
                parts.append(path.read_text(encoding="utf-8"))
        return "\n".join(parts)

    def test_no_captured_product_copy(self):
        text = self._all_text()
        for needle in FORBIDDEN:
            self.assertNotIn(needle, text)

    def test_runs_columns_present(self):
        html = (CONSOLE / "index.html").read_text(encoding="utf-8")
        for col in (
            "Incident",
            "Updated",
            "Affected operation",
            "Stage progress",
            "Outcome",
            "Next action",
        ):
            self.assertIn(col, html)
        self.assertIn("Invariant", html)
        self.assertIn("New run", html)

    def test_detail_has_five_stages(self):
        js = (CONSOLE / "app.js").read_text(encoding="utf-8")
        self.assertIn('["intake", "contract", "generate", "verify", "publish"]', js)
        self.assertIn("Intended behavior", js)
        self.assertIn("unbound", js)

    def test_css_tokens_and_no_page_min_width(self):
        css = (CONSOLE / "styles.css").read_text(encoding="utf-8")
        self.assertIn("#f6f3f0", css)
        self.assertIn("#175fff", css)
        self.assertIn("#08080A", css)
        self.assertIn("64px", css)
        self.assertIn("#1279F7", css)
        self.assertNotIn("min-width: 1000", css)
        self.assertIn("@media (max-width: 767px)", css)
        self.assertIn("@media (max-width: 1099px)", css)
