import asyncio
import json

import pytest

from models import LatencySegments, Outcome, Provider, Tier, TokenUsage, TraceLine
from tracer import Tracer


@pytest.fixture
def tracer(tmp_path):
    return Tracer(traces_file=tmp_path / "traces.jsonl")


def make_trace(**overrides) -> TraceLine:
    defaults = dict(
        provider=Provider.ollama,
        model="qwen3-vl:4b-instruct",
        tier=Tier.fast,
        latency=LatencySegments(),
    )
    defaults.update(overrides)
    return TraceLine(**defaults)


def test_start_registers_in_flight_trace(tracer):
    trace = make_trace()
    tracer.start(trace)
    assert tracer.get(trace.request_id) is not None
    assert tracer.in_flight_count() == 1


def test_get_unknown_request_returns_none(tracer):
    assert tracer.get("req_doesnotexist") is None


def test_mark_dispatch_complete_sets_latency(tracer):
    trace = make_trace()
    tracer.start(trace)
    tracer.mark_dispatch_complete(trace.request_id)
    assert tracer.get(trace.request_id).latency.t_dispatch_ms is not None


def test_mark_first_byte_only_records_first_call(tracer):
    trace = make_trace()
    tracer.start(trace)
    tracer.mark_first_byte(trace.request_id)
    first_value = tracer.get(trace.request_id).latency.ttfb_ms
    tracer.mark_first_byte(trace.request_id)  # second call should be a no-op
    assert tracer.get(trace.request_id).latency.ttfb_ms == first_value


def test_mark_first_content_token_sets_ttft(tracer):
    trace = make_trace()
    tracer.start(trace)
    tracer.mark_dispatch_complete(trace.request_id)
    tracer.mark_first_content_token(trace.request_id)
    assert tracer.get(trace.request_id).latency.ttft_ms is not None


def test_mark_stream_complete_sets_t_stream_and_tokens(tracer):
    trace = make_trace()
    tracer.start(trace)
    tracer.mark_first_content_token(trace.request_id)
    tokens = TokenUsage(input_text_tokens=10, output_tokens=20)
    tracer.mark_stream_complete(trace.request_id, tokens=tokens)
    updated = tracer.get(trace.request_id)
    assert updated.latency.t_stream_ms is not None
    assert updated.tokens.output_tokens == 20


def test_mark_stream_complete_without_first_token_leaves_t_stream_unset(tracer):
    # A response that was entirely filtered reasoning (no visible content
    # ever arrived) shouldn't get a fabricated t_stream_ms.
    trace = make_trace()
    tracer.start(trace)
    tracer.mark_stream_complete(trace.request_id, tokens=TokenUsage())
    assert tracer.get(trace.request_id).latency.t_stream_ms is None


def test_set_effort_updates_trace(tracer):
    trace = make_trace()
    tracer.start(trace)
    tracer.set_effort(trace.request_id, "low")
    assert tracer.get(trace.request_id).effort == "low"


def test_set_optimization_config_records_both_levers(tracer):
    trace = make_trace()
    tracer.start(trace)
    tracer.set_optimization_config(trace.request_id, max_tokens_used=256, ollama_keep_alive_used="30m")
    updated = tracer.get(trace.request_id)
    assert updated.max_tokens_used == 256
    assert updated.ollama_keep_alive_used == "30m"


def test_set_optimization_config_on_unknown_request_does_not_raise(tracer):
    tracer.set_optimization_config("req_doesnotexist", max_tokens_used=256, ollama_keep_alive_used=None)  # no-op, no crash


@pytest.mark.asyncio
async def test_finalize_writes_exactly_one_line(tracer):
    trace = make_trace()
    tracer.start(trace)
    await tracer.finalize(trace.request_id, Outcome.accepted, cost_usd=0.001)

    lines = tracer.read_all_completed()
    assert len(lines) == 1
    assert lines[0]["outcome"] == "accepted"
    assert lines[0]["cost_usd"] == 0.001


@pytest.mark.asyncio
async def test_finalize_is_safe_to_call_twice(tracer):
    # Supersede racing an outcome report — only the first call should write.
    trace = make_trace()
    tracer.start(trace)
    first = await tracer.finalize(trace.request_id, Outcome.accepted)
    second = await tracer.finalize(trace.request_id, Outcome.discarded)

    assert first is not None
    assert second is None  # already finalized — no-op, not an error
    assert len(tracer.read_all_completed()) == 1


@pytest.mark.asyncio
async def test_finalize_pops_from_in_flight(tracer):
    trace = make_trace()
    tracer.start(trace)
    assert tracer.in_flight_count() == 1
    await tracer.finalize(trace.request_id, Outcome.discarded)
    assert tracer.in_flight_count() == 0


@pytest.mark.asyncio
async def test_finalize_attaches_tokens_when_stream_never_completed(tracer):
    # The supersede/timeout path: tokens passed directly to finalize()
    # since mark_stream_complete() was never reached.
    trace = make_trace()
    tracer.start(trace)
    tokens = TokenUsage(input_text_tokens=5, input_image_tokens=258, output_tokens=3)
    await tracer.finalize(trace.request_id, Outcome.superseded, tokens=tokens)

    lines = tracer.read_all_completed()
    assert lines[0]["tokens"]["input_image_tokens"] == 258
    assert lines[0]["outcome"] == "superseded"


def test_read_all_completed_returns_empty_list_when_no_file(tmp_path):
    t = Tracer(traces_file=tmp_path / "does_not_exist.jsonl")
    assert t.read_all_completed() == []


@pytest.mark.asyncio
async def test_written_line_is_valid_single_line_json(tracer):
    trace = make_trace()
    tracer.start(trace)
    await tracer.finalize(trace.request_id, Outcome.accepted)

    with open(tracer._traces_file, "r") as f:
        raw_lines = f.readlines()
    assert len(raw_lines) == 1
    json.loads(raw_lines[0])  # must not raise