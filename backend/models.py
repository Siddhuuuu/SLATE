"""
Pydantic schema for Project SLATE.

Every model call in the app produces exactly one TraceLine, written once,
in full, to traces/*.jsonl. These types are the enforcement mechanism for
that promise — see tracer.py for how they get assembled and buffered.
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
    error = "error"
    cancelled = "cancelled"


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
    Mirrors whatever the provider's `usage` object actually returns.
    Fields are optional because providers differ — see PRD §3's note about
    inspecting the raw usage object before trusting a shape.
    """
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    image_tokens: Optional[int] = None       # split out where provider supports it
    reasoning_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated: bool = False  # True if image_tokens came from estimator.py, not the API

    @model_validator(mode="after")
    def _fill_total(self) -> "TokenUsage":
        if self.total_tokens is None:
            parts = [self.input_tokens, self.output_tokens]
            known = [p for p in parts if p is not None]
            if known:
                self.total_tokens = sum(known)
        return self


class LatencySegments(BaseModel):
    """
    All durations in milliseconds. Per PRD §7.1: never cross the client/server
    boundary with a timestamp, only ever a duration.
    """
    t_capture_ms: Optional[float] = None   # client: idle-trigger -> crop encoded
    t_dispatch_ms: Optional[float] = None  # server: request received -> provider call fired
    t_stream_ms: Optional[float] = None    # server: provider call fired -> stream complete
    t_render_ms: Optional[float] = None    # client: first stream chunk -> draft painted

    @property
    def t_total_ms(self) -> Optional[float]:
        parts = [self.t_capture_ms, self.t_dispatch_ms, self.t_stream_ms, self.t_render_ms]
        known = [p for p in parts if p is not None]
        return sum(known) if known else None


# ---------------------------------------------------------------------------
# Request / outcome payloads (API surface)
# ---------------------------------------------------------------------------

class CreateRequestIn(BaseModel):
    image_b64: str  # WebP crop, base64-encoded, no data: prefix
    image_width_px: Optional[int] = None   # encoded crop dimensions, for estimator.py fallback
    image_height_px: Optional[int] = None
    context: RegionContext
    t_capture_ms: Optional[float] = None
    provider_override: Optional[Provider] = None  # experiment harness only — see router.py


class CreateRequestOut(BaseModel):
    request_id: str
    tier: Tier
    provider: Provider
    model: str


class OutcomeIn(BaseModel):
    outcome: Literal["accepted", "discarded"]
    t_render_ms: Optional[float] = None


class OutcomeOut(BaseModel):
    request_id: str
    outcome: Outcome
    trace_written: bool


# ---------------------------------------------------------------------------
# The trace line itself — one of these per request, written once
# ---------------------------------------------------------------------------

class TraceLine(BaseModel):
    request_id: str = Field(default_factory=new_request_id)
    created_at: str = Field(default_factory=_now_iso)
    provider: Provider
    model: str
    tier: Tier
    routing_reason: str = ""          # why router.py picked this tier — see router.py
    outcome: Outcome = Outcome.pending
    context: Optional[RegionContext] = None
    tokens: Optional[TokenUsage] = None
    latency: Optional[LatencySegments] = None
    cost_usd: Optional[float] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True)
