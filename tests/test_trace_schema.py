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
    Trigger,
    TraceInput,
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
    usage = TokenUsage(input_text_tokens=100, input_image_tokens=20, output_tokens=50)
    assert usage.total_tokens == 170


def test_token_usage_respects_explicit_total():
    usage = TokenUsage(input_text_tokens=100, output_tokens=50, total_tokens=999)
    assert usage.total_tokens == 999


def test_token_usage_all_none_stays_none():
    usage = TokenUsage()
    assert usage.total_tokens is None


def test_token_usage_input_tokens_convenience_sum():
    usage = TokenUsage(input_text_tokens=100, input_image_tokens=50)
    assert usage.input_tokens == 150


def test_token_usage_input_tokens_none_when_both_unknown():
    usage = TokenUsage(output_tokens=10)
    assert usage.input_tokens is None


def test_token_usage_default_source_is_estimated():
    usage = TokenUsage(input_image_tokens=100)
    assert usage.input_image_source == "estimated"


def test_latency_total_sums_known_segments_excluding_ttfb():
    # t_total_ms is t_capture + t_dispatch + ttft + t_stream + t_render —
    # deliberately excludes ttfb, which overlaps with ttft rather than
    # chaining after it (see models.py's LatencySegments docstring).
    latency = LatencySegments(
        t_capture_ms=10, t_dispatch_ms=20, ttfb_ms=999, ttft_ms=5, t_stream_ms=None, t_render_ms=30
    )
    assert latency.t_total_ms == 65  # 10+20+5+30, ttfb (999) excluded


def test_latency_total_none_when_nothing_known():
    latency = LatencySegments()
    assert latency.t_total_ms is None


def test_latency_e2e_is_independent_field():
    latency = LatencySegments(t_capture_ms=10, e2e_ms=5000)
    assert latency.e2e_ms == 5000


def test_trace_line_defaults():
    trace = TraceLine(provider=Provider.gemini, model="gemini-3.6-flash", tier=Tier.heavy)
    assert trace.request_id.startswith("req_")
    assert trace.session_id.startswith("ses_")
    assert trace.outcome == Outcome.pending.value  # use_enum_values=True
    assert trace.trigger == Trigger.idle_pause.value
    assert trace.created_at  # ISO string present


def test_trace_line_serializes_to_valid_json_line():
    trace = TraceLine(
        provider=Provider.ollama,
        model="qwen3-vl:4b",
        tier=Tier.fast,
        trigger=Trigger.explicit,
        routing_reason="within fast-tier thresholds",
        context=make_context(),
        input=TraceInput(crop_px=(512, 512), format="png", bytes=48000, zoom=1.0, stroke_count=5, prompt_chars=100),
        tokens=TokenUsage(input_text_tokens=10, input_image_tokens=258, output_tokens=20),
        latency=LatencySegments(t_capture_ms=5, t_dispatch_ms=3, ttfb_ms=50, ttft_ms=80, t_stream_ms=400, t_render_ms=12, e2e_ms=550),
        cost_usd=0.0,
        outcome=Outcome.accepted,
    )
    line = trace.model_dump_json()
    parsed = json.loads(line)  # must be exactly one JSON object per line
    assert parsed["request_id"] == trace.request_id
    assert parsed["provider"] == "ollama"
    assert parsed["outcome"] == "accepted"
    assert parsed["trigger"] == "explicit"
    assert parsed["tokens"]["input_text_tokens"] == 10
    assert parsed["tokens"]["input_image_tokens"] == 258
    assert parsed["latency"]["ttft_ms"] == 80
    assert parsed["input"]["crop_px"] == [512, 512]


def test_trace_line_requires_provider_model_tier():
    with pytest.raises(ValidationError):
        TraceLine()  # type: ignore[call-arg]


def test_trace_line_outcome_supports_superseded_and_timeout():
    superseded = TraceLine(provider=Provider.gemini, model="x", tier=Tier.heavy, outcome=Outcome.superseded)
    timeout = TraceLine(provider=Provider.gemini, model="x", tier=Tier.heavy, outcome=Outcome.timeout)
    assert superseded.outcome == "superseded"
    assert timeout.outcome == "timeout"


def test_region_context_defaults_are_safe():
    ctx = make_context(stroke_count=0, ink_density=0.0)
    assert ctx.nearby_shape_types == []
    assert ctx.nearby_accepted_draft_ids == []
