"""
Pydantic schema for Project SLATE.

Every model call in the app produces exactly one TraceLine, written once,
in full, to traces/*.jsonl. These types are the enforcement mechanism for
that promise — see tracer.py for how they get assembled and buffered.

This version matches the actual assignment brief's documented trace
schema (Section 5, B4) field-for-field where the brief names a field
explicitly — session_id, trigger, effort, config_id, the six named
latency segments, the six named token fields, and the six-value outcome
enum. Where the brief's schema doesn't specify a Python-side detail
(e.g. how "in" is split for cost.py's formula), that choice is
documented at the point it's made, not here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


def new_session_id() -> str:
    return f"ses_{uuid4().hex[:12]}"


# One session_id per backend process lifetime — matches the brief's
# session_id field, which groups requests from one running instance of
# the app. Regenerates on restart; that's the correct behavior, not a
# limitation to fix (a restart is a new session).
CURRENT_SESSION_ID = new_session_id()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Provider(str, Enum):
    gemini = "gemini"
    ollama = "ollama"
    openrouter = "openrouter"


class Tier(str, Enum):
    fast = "fast"       # small/local, cheap
    heavy = "heavy"      # larger/cloud, expensive


class Outcome(str, Enum):
    pending = "pending"
    accepted = "accepted"
    discarded = "discarded"
    cancelled = "cancelled"    # reserved for a future explicit user-cancel action
    superseded = "superseded"  # a newer capture replaced this one before it settled — see useDraftLifecycle.ts
    timeout = "timeout"        # exceeded the server-side request budget — see main.py REQUEST_TIMEOUT_S
    error = "error"


class Trigger(str, Enum):
    idle_pause = "idle_pause"  # default idle-timer path
    explicit = "explicit"      # "Generate now" button
    refine = "refine"          # a new capture superseding an already-unsettled draft for the same region


# ---------------------------------------------------------------------------
# Region of interest (what got sent to the model)
# ---------------------------------------------------------------------------

class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class RegionContext(BaseModel):
    """Non-image context sent alongside the crop — see PRD §6."""
    bbox: BoundingBox
    zoom: float = 1.0
    source: Literal["selection", "ink_cluster", "viewport"] = "ink_cluster"
    nearby_shape_types: list[str] = Field(default_factory=list)
    nearby_accepted_draft_ids: list[str] = Field(default_factory=list)
    stroke_count: int = 0
    ink_density: float = 0.0  # strokes per unit area, used by router.py


# ---------------------------------------------------------------------------
# Token / cost accounting
# ---------------------------------------------------------------------------

class TokenUsage(BaseModel):
    """
    Matches the brief's documented token fields exactly:
    input_text, input_image, input_image_source, output, reasoning,
    cache_read, total.

    input_image_source is "reported" only when a provider's own usage
    object splits out image tokens directly (confirmed: none of Gemini's
    OpenAI-compat endpoint, Gemini's usage_metadata as exposed by
    google-genai, or Ollama currently do this reliably — see
    scripts/validate_image_token_estimator.py). It is "estimated" —
    the overwhelmingly common case right now — whenever estimator.py's
    tiling-formula estimate is what's actually in this field.
    """
    input_text_tokens: Optional[int] = None
    input_image_tokens: Optional[int] = None
    input_image_source: Literal["reported", "estimated"] = "estimated"
    output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = 0
    total_tokens: Optional[int] = None

    @model_validator(mode="after")
    def _fill_total(self) -> "TokenUsage":
        if self.total_tokens is None:
            parts = [
                self.input_text_tokens,
                self.input_image_tokens,
                self.output_tokens,
                self.reasoning_tokens,
            ]
            known = [p for p in parts if p is not None]
            if known:
                self.total_tokens = sum(known)
        return self

    @property
    def input_tokens(self) -> Optional[int]:
        """Convenience sum — input_text + input_image. Not a brief field
        itself, just avoids repeating `(a or 0) + (b or 0)` at call sites."""
        parts = [self.input_text_tokens, self.input_image_tokens]
        known = [p for p in parts if p is not None]
        return sum(known) if known else None


class LatencySegments(BaseModel):
    """
    All durations in milliseconds. Per PRD §7.1 / brief B1: never cross
    the client/server boundary with a timestamp, only ever a duration.

    Matches the brief's six named segments plus e2e:
        t_capture   client: trigger fires -> payload encoded
        t_dispatch  server: payload received -> provider call fired
        ttfb        server: provider call fired -> first byte of any kind received
        ttft        server: provider call fired -> first CONTENT token received
                    (post think-tag-filtering — see main.py/think_filter.py.
                    For a reasoning model, ttft can be well past ttfb; that
                    gap IS the hidden-reasoning cost made visible as latency,
                    which is exactly the kind of thing this segment exists
                    to surface, not average away.)
        t_stream    server: first content token -> last content token
        t_render    client: last content token -> draft painted on canvas
        e2e         client: trigger fires -> draft painted on canvas
                    (measured DIRECTLY as one client-side stopwatch, per
                    the brief's own definition, not inferred by summing
                    the other six — ttfb and ttft overlap with each other,
                    so a naive sum would double-count.)
    """
    t_capture_ms: Optional[float] = None
    t_dispatch_ms: Optional[float] = None
    ttfb_ms: Optional[float] = None
    ttft_ms: Optional[float] = None
    t_stream_ms: Optional[float] = None
    t_render_ms: Optional[float] = None
    e2e_ms: Optional[float] = None

    @property
    def t_total_ms(self) -> Optional[float]:
        """Sum of the sequential parts (t_capture + t_dispatch + ttft +
        t_stream + t_render) — a sanity-check cross-reference against the
        directly-measured e2e_ms, not the authoritative number itself.
        Deliberately excludes ttfb, which overlaps with ttft rather than
        chaining after it."""
        parts = [self.t_capture_ms, self.t_dispatch_ms, self.ttft_ms, self.t_stream_ms, self.t_render_ms]
        known = [p for p in parts if p is not None]
        return sum(known) if known else None


# ---------------------------------------------------------------------------
# Request / outcome payloads (API surface)
# ---------------------------------------------------------------------------

class CreateRequestIn(BaseModel):
    image_b64: str  # PNG crop, base64-encoded, no data: prefix
    image_width_px: Optional[int] = None   # encoded crop dimensions, for estimator.py fallback
    image_height_px: Optional[int] = None
    context: RegionContext
    t_capture_ms: Optional[float] = None
    trigger: Trigger = Trigger.idle_pause
    prompt_chars: Optional[int] = None  # length of the text portion of the prompt actually sent
    config_id: Optional[str] = None     # ties this request to a B5 experiment arm — see run_experiment.py
    provider_override: Optional[Provider] = None  # experiment harness only — see router.py

    # --- B5 optimization levers (Section 5's "implement at least two
    # optimisations... measure before/after") — both per-REQUEST, not
    # env-var-plus-restart, specifically so run_experiment.py can
    # interleave on/off exactly like it already interleaves provider
    # arms. A restart-based toggle would force all-baseline-then-all-
    # optimized, which is the exact contamination pattern the brief
    # warns against for provider arms; there's no principled reason to
    # accept that risk here just because it's a different kind of arm.
    max_tokens_override: Optional[int] = None    # None = baseline (512, main.py's default)
    ollama_keep_alive: Optional[str] = None       # None = Ollama's own default (effectively "off")


class CreateRequestOut(BaseModel):
    request_id: str
    tier: Tier
    provider: Provider
    model: str


class OutcomeIn(BaseModel):
    outcome: Literal["accepted", "discarded"]
    t_render_ms: Optional[float] = None
    e2e_ms: Optional[float] = None


class OutcomeOut(BaseModel):
    request_id: str
    outcome: Outcome
    trace_written: bool


# ---------------------------------------------------------------------------
# The trace line itself — one of these per request, written once
# ---------------------------------------------------------------------------

class TraceInput(BaseModel):
    """The `input` sub-object of a trace line, per the brief's schema."""
    crop_px: tuple[int, int] = (0, 0)
    format: str = "png"
    bytes: int = 0
    zoom: float = 1.0
    stroke_count: int = 0
    prompt_chars: int = 0


class TraceLine(BaseModel):
    request_id: str = Field(default_factory=new_request_id)
    session_id: str = Field(default_factory=lambda: CURRENT_SESSION_ID)
    created_at: str = Field(default_factory=_now_iso)  # brief calls this ts_start
    trigger: Trigger = Trigger.idle_pause
    provider: Provider
    model: str
    tier: Tier
    effort: str = "n/a"        # reasoning_effort value sent (Gemini) or "n/a" (Ollama/OpenRouter)
    config_id: Optional[str] = None
    max_tokens_used: int = 512           # actual cap sent — records the real value, not inferred from config_id naming
    ollama_keep_alive_used: Optional[str] = None  # actual keep_alive sent, None if not requested (Ollama's own default applied)
    routing_reason: str = ""   # why router.py picked this tier — see router.py
    outcome: Outcome = Outcome.pending
    context: Optional[RegionContext] = None
    input: Optional[TraceInput] = None
    tokens: Optional[TokenUsage] = None
    latency: Optional[LatencySegments] = None
    cost_usd: Optional[float] = None
    error_message: Optional[str] = None
    retries: int = 0

    model_config = ConfigDict(use_enum_values=True)