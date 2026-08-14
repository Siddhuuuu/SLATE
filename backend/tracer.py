"""
tracer.py — PRD §7.1 / §7.2, extended to match the brief's six-segment
latency model (B1).

The clock-skew rule: never send absolute timestamps across the client/
server boundary, only durations. This module owns the server side of that
contract — it buffers a TraceLine per request_id in memory, and only
appends the JSONL line once the trace is complete (outcome reported,
cancelled, timed out, or errored). That's what keeps "one line per
request" honest instead of mutating an already-appended file.

This also doubles as the in-memory source of truth for the live metrics
panel (PRD §7.4) — the JSONL file is the durable copy, not what the panel
reads from.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from models import LatencySegments, Outcome, TokenUsage, TraceLine

TRACES_DIR = Path(__file__).parent / "traces"
TRACES_FILE = TRACES_DIR / "traces.jsonl"


class Tracer:
    """
    Single process-wide instance (see main.py). Not thread-safe across
    multiple worker processes — this app is explicitly single-user/local,
    so that's a documented non-goal, not an oversight.
    """

    def __init__(self, traces_file: Path = TRACES_FILE):
        self._traces_file = traces_file
        self._traces_file.parent.mkdir(parents=True, exist_ok=True)
        self._buffer: dict[str, TraceLine] = {}
        # Per-request monotonic timestamps, named. Segments are computed
        # as differences between these at the point each is recorded, so
        # a request that never reaches a later stage (cancelled, timed
        # out) still has correct data for every stage it DID reach.
        self._timestamps: dict[str, dict[str, float]] = {}
        self._lock = asyncio.Lock()

    # -- lifecycle -----------------------------------------------------

    def start(self, trace: TraceLine) -> None:
        """Register a new in-flight trace. Called from POST /requests."""
        self._buffer[trace.request_id] = trace
        self._timestamps[trace.request_id] = {"start": time.monotonic()}

    def get(self, request_id: str) -> Optional[TraceLine]:
        return self._buffer.get(request_id)

    def mark_dispatch_complete(self, request_id: str) -> None:
        """Call the instant the provider call is actually fired."""
        trace = self._buffer.get(request_id)
        ts = self._timestamps.get(request_id)
        if trace is None or ts is None or trace.latency is None:
            return
        now = time.monotonic()
        ts["dispatch_fired"] = now
        trace.latency.t_dispatch_ms = (now - ts["start"]) * 1000

    def mark_first_byte(self, request_id: str) -> None:
        """Call on the very first chunk received from the provider, even
        an empty/role-only one — this is ttfb, distinct from ttft."""
        trace = self._buffer.get(request_id)
        ts = self._timestamps.get(request_id)
        if trace is None or ts is None or trace.latency is None:
            return
        if "first_byte" in ts:
            return  # only the first call counts
        now = time.monotonic()
        ts["first_byte"] = now
        dispatch_fired = ts.get("dispatch_fired", ts["start"])
        trace.latency.ttfb_ms = (now - dispatch_fired) * 1000

    def mark_first_content_token(self, request_id: str) -> None:
        """Call on the first chunk that contains actual visible content
        (post think-tag-filtering) — this is ttft. For a reasoning model,
        this can be well after mark_first_byte(); that gap is real signal,
        not noise, see models.py's LatencySegments docstring."""
        trace = self._buffer.get(request_id)
        ts = self._timestamps.get(request_id)
        if trace is None or ts is None or trace.latency is None:
            return
        if "first_token" in ts:
            return
        now = time.monotonic()
        ts["first_token"] = now
        dispatch_fired = ts.get("dispatch_fired", ts["start"])
        trace.latency.ttft_ms = (now - dispatch_fired) * 1000

    def mark_stream_complete(
        self, request_id: str, tokens: Optional[TokenUsage] = None
    ) -> None:
        """t_stream = first content token -> last content token. If no
        content token was ever seen (e.g. the whole response was
        reasoning that got filtered out), t_stream is left unset rather
        than guessed."""
        trace = self._buffer.get(request_id)
        ts = self._timestamps.get(request_id)
        if trace is None or ts is None or trace.latency is None:
            return
        now = time.monotonic()
        if "first_token" in ts:
            trace.latency.t_stream_ms = (now - ts["first_token"]) * 1000
        if tokens is not None:
            trace.tokens = tokens

    def set_effort(self, request_id: str, effort: str) -> None:
        trace = self._buffer.get(request_id)
        if trace is not None:
            trace.effort = effort

    def set_optimization_config(
        self, request_id: str, max_tokens_used: int, ollama_keep_alive_used: str | None
    ) -> None:
        """Records the actual B5 optimization-lever values used for this
        request, at dispatch time — not inferred later from config_id
        naming, which would be fragile (a harness typo silently breaks
        attribution)."""
        trace = self._buffer.get(request_id)
        if trace is not None:
            trace.max_tokens_used = max_tokens_used
            trace.ollama_keep_alive_used = ollama_keep_alive_used

    async def finalize(
        self,
        request_id: str,
        outcome: Outcome,
        t_render_ms: Optional[float] = None,
        e2e_ms: Optional[float] = None,
        cost_usd: Optional[float] = None,
        error_message: Optional[str] = None,
        tokens: Optional[TokenUsage] = None,
    ) -> Optional[TraceLine]:
        """
        Completes and writes the trace line exactly once. Safe to call
        more than once for the same request_id (e.g. a supersede racing
        an outcome report) — only the first call actually writes.

        `tokens`, when passed here, is for the cancelled/superseded/
        timeout path — a request that never reached mark_stream_complete
        can still have partial/estimated token usage attached, which is
        what makes WTR (wasted token ratio) meaningful instead of every
        aborted request silently costing "0 tokens" in the trace.
        """
        async with self._lock:
            trace = self._buffer.pop(request_id, None)
            self._timestamps.pop(request_id, None)
            if trace is None:
                return None  # already finalized, or never started

            trace.outcome = outcome
            if t_render_ms is not None and trace.latency:
                trace.latency.t_render_ms = t_render_ms
            if e2e_ms is not None and trace.latency:
                trace.latency.e2e_ms = e2e_ms
            if cost_usd is not None:
                trace.cost_usd = cost_usd
            if error_message is not None:
                trace.error_message = error_message
            if tokens is not None and trace.tokens is None:
                trace.tokens = tokens

            self._write_line(trace)
            return trace

    def _write_line(self, trace: TraceLine) -> None:
        with open(self._traces_file, "a") as f:
            f.write(trace.model_dump_json() + "\n")

    # -- live panel support ---------------------------------------------

    def in_flight_count(self) -> int:
        return len(self._buffer)

    def read_all_completed(self) -> list[dict]:
        if not self._traces_file.exists():
            return []
        lines = []
        with open(self._traces_file, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(json.loads(line))
        return lines


tracer = Tracer()