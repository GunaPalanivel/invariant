"""ModelClient failovers without calling live APIs."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invariant.llm import ModelClient, StubLLMClient


class _Boom:
    provider = "gemini"
    last_usage = {}

    def complete_json(self, system: str, user: str) -> dict:
        raise RuntimeError("primary down")

    def complete_text(self, system: str, user: str, max_tokens: int = 4000) -> str:
        raise RuntimeError("primary down")


class TestModelClient(unittest.TestCase):
    def test_fallback_after_primary_error(self):
        stub = StubLLMClient({"hi": {"destination": "C-RELEASES"}})
        client = ModelClient(_Boom(), stub)
        parsed = client.complete_json("sys", "hi")
        self.assertEqual(parsed["destination"], "C-RELEASES")
        self.assertEqual(client.provider, "stub")
        self.assertEqual(client.origin_tag(), "model:stub")
