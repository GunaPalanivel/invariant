"""LLM seam. Production keys stay in the broker process, never in generated tests."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Protocol

from invariant.envload import load_env

load_env()

PINNED_MODEL = os.environ.get("INVARIANT_MODEL", "gemini-3.7-flash")
FALLBACK_MODEL = os.environ.get("INVARIANT_FALLBACK_MODEL", "openai/gpt-oss-120b")
GROQ_MAX_TOKENS_CAP = 1536


class LLMClient(Protocol):
    provider: str

    def complete_json(self, system: str, user: str) -> dict: ...

    def complete_text(self, system: str, user: str, max_tokens: int = 4000) -> str: ...


class StubLLMClient:
    provider = "stub"

    def __init__(self, responses: dict[str, dict]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str]] = []
        self.last_usage: dict[str, int] = {}

    def complete_json(self, system: str, user: str) -> dict:
        self.calls.append((system, user))
        matches = [key for key in self._responses if key in user]
        if not matches:
            raise KeyError("StubLLMClient has no matching response")
        return self._responses[max(matches, key=len)]

    def complete_text(self, system: str, user: str, max_tokens: int = 4000) -> str:
        parsed = self.complete_json(system, user)
        if isinstance(parsed, dict) and "python" in parsed:
            return str(parsed["python"])
        raise KeyError("StubLLMClient has no python text for this prompt")


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```python").removeprefix("```").strip()
        cleaned = cleaned.removesuffix("```").strip()
    return cleaned


def _parse_json_text(text: str) -> dict:
    cleaned = _strip_fences(text)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("model JSON was not an object")
    return parsed


class GeminiClient:
    provider = "gemini"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self._api_key = key
        self._model = model or PINNED_MODEL
        self.last_usage: dict[str, int] = {}

    def _models(self) -> list[str]:
        names = [self._model]
        if self._model != "gemini-flash-latest":
            names.append("gemini-flash-latest")
        return names

    def _record_usage(self, payload: dict) -> None:
        usage = payload.get("usageMetadata") or {}
        self.last_usage = {
            "input_tokens": int(self.last_usage.get("input_tokens", 0))
            + int(usage.get("promptTokenCount") or 0),
            "output_tokens": int(self.last_usage.get("output_tokens", 0))
            + int(usage.get("candidatesTokenCount") or 0),
        }

    def _extract_text(self, payload: dict) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = (((candidates[0] or {}).get("content") or {}).get("parts")) or []
        texts = [str(part.get("text") or "") for part in parts if part.get("text")]
        if not texts:
            finish = (candidates[0] or {}).get("finishReason")
            raise RuntimeError(f"Gemini returned empty text ({finish})")
        return "\n".join(texts)

    def _generate_rest(self, model: str, system: str, user: str, max_tokens: int, json_mode: bool) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        def post(with_thinking: bool) -> dict:
            generation: dict = {"maxOutputTokens": max_tokens}
            if json_mode:
                generation["responseMimeType"] = "application/json"
            if with_thinking:
                generation["thinkingConfig"] = {"thinkingLevel": "LOW"}
            body = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": generation,
            }
            request = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-goog-api-key": self._api_key,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                exc.read()
                raise RuntimeError(f"Gemini HTTP {exc.code}") from None

        try:
            payload = post(True)
        except RuntimeError as exc:
            if "HTTP 400" not in str(exc):
                raise
            payload = post(False)
        self._record_usage(payload)
        return self._extract_text(payload)

    def _generate(self, system: str, user: str, max_tokens: int, json_mode: bool) -> str:
        last_error: Exception | None = None
        for model in self._models():
            try:
                return self._generate_rest(model, system, user, max_tokens, json_mode)
            except Exception as exc:
                last_error = exc
                message = str(exc).lower()
                if "404" in message or "not found" in message or "not_found" in message:
                    continue
                raise
        raise last_error or RuntimeError("Gemini complete failed")

    def complete_text(self, system: str, user: str, max_tokens: int = 4000) -> str:
        budget = max(int(max_tokens or 2048), 2048)
        try:
            return self._generate(system, user, budget, json_mode=False)
        except RuntimeError as exc:
            if "empty text" not in str(exc):
                raise
            return self._generate(system, user, max(budget * 2, 4096), json_mode=False)

    def complete_json(self, system: str, user: str) -> dict:
        text = self._generate(system, user, max_tokens=2048, json_mode=True)
        return _parse_json_text(text)


class GroqClient:
    provider = "groq"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        try:
            from groq import Groq
        except ImportError as exc:
            raise RuntimeError("groq package is not installed") from exc
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set")
        self._client = Groq(api_key=key)
        self._model = model or FALLBACK_MODEL
        self.last_usage: dict[str, int] = {}

    def _record_usage(self, response: object) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.last_usage = {
            "input_tokens": int(self.last_usage.get("input_tokens", 0))
            + int(getattr(usage, "prompt_tokens", 0) or 0),
            "output_tokens": int(self.last_usage.get("output_tokens", 0))
            + int(getattr(usage, "completion_tokens", 0) or 0),
        }

    def complete_text(self, system: str, user: str, max_tokens: int = 4000) -> str:
        capped = min(int(max_tokens or GROQ_MAX_TOKENS_CAP), GROQ_MAX_TOKENS_CAP)
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=capped,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        self._record_usage(response)
        choice = response.choices[0].message.content
        if not choice:
            raise RuntimeError("Groq returned empty text")
        return choice

    def complete_json(self, system: str, user: str) -> dict:
        capped = min(1000, GROQ_MAX_TOKENS_CAP)
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=capped,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        self._record_usage(response)
        choice = response.choices[0].message.content
        if not choice:
            raise RuntimeError("Groq returned empty JSON")
        return _parse_json_text(choice)


class ModelClient:
    """Gemini primary, Groq fallback. Per-call failover. Never prints secrets."""

    def __init__(
        self,
        primary: LLMClient | None,
        fallback: LLMClient | None,
    ) -> None:
        if primary is None and fallback is None:
            raise RuntimeError("no live model client configured")
        self._primary = primary
        self._fallback = fallback
        self.provider = "gemini" if primary is not None else "groq"
        self.providers_used: list[str] = []
        self.last_usage: dict[str, int] = {}
        self.last_error: str | None = None

    def origin_tag(self) -> str:
        if not self.providers_used:
            return f"model:{self.provider}"
        return "model:" + "+".join(self.providers_used)

    def _merge_usage(self, client: LLMClient) -> None:
        usage = dict(getattr(client, "last_usage", {}) or {})
        self.last_usage = {
            "input_tokens": int(self.last_usage.get("input_tokens", 0)) + int(usage.get("input_tokens", 0) or 0),
            "output_tokens": int(self.last_usage.get("output_tokens", 0)) + int(usage.get("output_tokens", 0) or 0),
        }

    def _mark(self, client: LLMClient) -> None:
        name = getattr(client, "provider", "model")
        self.provider = name
        if name not in self.providers_used:
            self.providers_used.append(name)
        self._merge_usage(client)

    def _ordered(self) -> list[LLMClient]:
        clients: list[LLMClient] = []
        if self._primary is not None:
            clients.append(self._primary)
        if self._fallback is not None:
            clients.append(self._fallback)
        return clients

    def complete_text(self, system: str, user: str, max_tokens: int = 4000) -> str:
        errors: list[str] = []
        for client in self._ordered():
            try:
                text = client.complete_text(system, user, max_tokens=max_tokens)
                self._mark(client)
                return text
            except Exception as exc:
                errors.append(f"{getattr(client, 'provider', type(client).__name__)}:{type(exc).__name__}")
                self.last_error = type(exc).__name__
        raise RuntimeError("all live model clients failed: " + ",".join(errors))

    def complete_json(self, system: str, user: str) -> dict:
        errors: list[str] = []
        for client in self._ordered():
            try:
                parsed = client.complete_json(system, user)
                self._mark(client)
                return parsed
            except Exception as exc:
                errors.append(f"{getattr(client, 'provider', type(client).__name__)}:{type(exc).__name__}")
                self.last_error = type(exc).__name__
        raise RuntimeError("all live model clients failed: " + ",".join(errors))
