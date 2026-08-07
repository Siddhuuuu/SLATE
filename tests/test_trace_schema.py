import json

import pytest
from pydantic import ValidationError

from models import (
    BoundingBox,
    LatencySegments,
    Outcome,
    Provider,
    RegionContext,
    Tier,
    TokenUsage,
    TraceLine,
)


def make_context(**overrides) -> RegionContext:
    defaults = dict(
        bbox=BoundingBox(x=0, y=0, width=512, height=512),
        zoom=1.0,
        source="ink_cluster",
        stroke_count=5,
        ink_density=0.1,
    )
    defaults.update(overrides)
    return RegionContext(**defaults)


def test_token_usage_fills_total_from_parts():
    usage = TokenUsage(input_tokens=100, output_tokens=50)
    assert usage.total_tokens == 150


def test_token_usage_respects_explicit_total():
    usage = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=999)
    assert usage.total_tokens == 999


def test_token_usage_all_none_stays_none():
    usage = TokenUsage()
    assert usage.total_tokens is None


def test_latency_total_sums_known_segments():
    latency = LatencySegments(t_capture_ms=10, t_dispatch_ms=20, t_stream_ms=None, t_render_ms=30)
    assert latency.t_total_ms == 60


def test_latency_total_none_when_nothing_known():
    latency = LatencySegments()
    assert latency.t_total_ms is None


def test_trace_line_defaults():
    trace = TraceLine(provider=Provider.gemini, model="gemini-3-flash", tier=Tier.heavy)
    assert trace.request_id.startswith("req_")
    assert trace.outcome == Outcome.pending.value  # use_enum_values=True
    assert trace.created_at  # ISO string present


def test_trace_line_serializes_to_valid_json_line():
    trace = TraceLine(
        provider=Provider.ollama,
        model="qwen3-vl:4b",
        tier=Tier.fast,
        routing_reason="within fast-tier thresholds",
        context=make_context(),
        tokens=TokenUsage(input_tokens=10, output_tokens=20),
        latency=LatencySegments(t_capture_ms=5, t_dispatch_ms=3, t_stream_ms=400, t_render_ms=12),
        cost_usd=0.0,
        outcome=Outcome.accepted,
    )
    line = trace.model_dump_json()
    parsed = json.loads(line)  # must be exactly one JSON object per line
    assert parsed["request_id"] == trace.request_id
    assert parsed["provider"] == "ollama"
    assert parsed["outcome"] == "accepted"
    assert parsed["tokens"]["input_tokens"] == 10


def test_trace_line_requires_provider_model_tier():
    with pytest.raises(ValidationError):
        TraceLine()  # type: ignore[call-arg]


def test_region_context_defaults_are_safe():
    ctx = make_context(stroke_count=0, ink_density=0.0)
    assert ctx.nearby_shape_types == []
    assert ctx.nearby_accepted_draft_ids == []
