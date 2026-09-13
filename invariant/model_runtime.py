"""Choose live Gemini (primary) then Groq (fallback) vs disclosed template. Never prints secrets."""

from __future__ import annotations

import os

from invariant.envload import load_env
from invariant.llm import FALLBACK_MODEL, GeminiClient, GroqClient, LLMClient, ModelClient, PINNED_MODEL


def live_model_flag() -> bool:
    load_env()
    flag = os.environ.get("INVARIANT_USE_LIVE_MODEL", "1").strip().lower()
    return flag not in {"0", "false", "no", "off"}


def gemini_configured() -> bool:
    load_env()
    return bool(os.environ.get("GEMINI_API_KEY"))


def groq_configured() -> bool:
    load_env()
    return bool(os.environ.get("GROQ_API_KEY"))


def use_live_model() -> bool:
    return live_model_flag() and (gemini_configured() or groq_configured())


def origin_for(client: LLMClient | None) -> str:
    if client is None:
        return "disclosed_template"
    tag = getattr(client, "origin_tag", None)
    if callable(tag):
        return str(tag())
    provider = getattr(client, "provider", None)
    if provider:
        return f"model:{provider}"
    return "model"


def try_gemini_client() -> LLMClient | None:
    if not gemini_configured():
        return None
    try:
        return GeminiClient(model=PINNED_MODEL)
    except Exception:
        return None


def try_groq_client() -> LLMClient | None:
    if not groq_configured():
        return None
    try:
        return GroqClient(model=FALLBACK_MODEL)
    except Exception:
        return None


def try_live_client() -> LLMClient | None:
    if not use_live_model():
        return None
    primary = try_gemini_client()
    fallback = try_groq_client()
    if primary is None and fallback is None:
        return None
    try:
        return ModelClient(primary, fallback)
    except Exception:
        return None
