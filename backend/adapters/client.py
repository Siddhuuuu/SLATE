"""
adapters/client.py — one adapter class, three provider configs.

Gemini and Ollama both expose OpenAI-compatible endpoints, so there is
exactly one client shape here, not three. OpenRouter is included as a
scoped third option for the router feature's cross-family access only
(PRD §3, §9) — it is never used inside the B5 experiment.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from openai import AsyncOpenAI

ProviderName = Literal["gemini", "ollama", "openrouter"]

PROVIDER_CONFIG: dict[str, dict] = {
    "gemini": dict(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key=os.environ.get("GEMINI_API_KEY", ""),
        model="gemini-3-flash",
    ),
    "ollama": dict(
        base_url="http://localhost:11434/v1",
        api_key="ollama",  # unused, SDK requires a non-empty value
        model=os.environ.get("OLLAMA_MODEL", "qwen3-vl:4b"),
    ),
    "openrouter": dict(  # router-feature only — see PRD §9, kept out of B5
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        model="google/gemini-flash-1.5",
    ),
}


@lru_cache(maxsize=None)
def get_client(provider: ProviderName) -> AsyncOpenAI:
    """
    Returns a cached AsyncOpenAI client configured for `provider`. Cached
    per-provider so repeated calls (every request in the app's lifetime)
    don't re-open connections needlessly.
    """
    if provider not in PROVIDER_CONFIG:
        raise ValueError(f"Unknown provider '{provider}'. Known: {list(PROVIDER_CONFIG)}")
    cfg = PROVIDER_CONFIG[provider]
    return AsyncOpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])


def resolve_auto_provider() -> ProviderName:
    """
    `.env` sets MODEL_PROVIDER=gemini|ollama|auto. This resolves `auto` at
    startup time (evaluated once, per PRD §3) — Gemini if GEMINI_API_KEY is
    set, else Ollama. This function is NOT used by the B5 experiment
    harness, which always pins an explicit --provider flag.
    """
    configured = os.environ.get("MODEL_PROVIDER", "auto").lower()
    if configured in ("gemini", "ollama", "openrouter"):
        return configured  # type: ignore[return-value]
    if configured != "auto":
        raise ValueError(f"Unknown MODEL_PROVIDER '{configured}'")
    return "gemini" if os.environ.get("GEMINI_API_KEY") else "ollama"


def model_for(provider: ProviderName) -> str:
    return PROVIDER_CONFIG[provider]["model"]
