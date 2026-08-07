"""
tracer.py — PRD §7.1 / §7.2.

The clock-skew rule: never send absolute timestamps across the client/
server boundary, only durations. This module owns the server side of that
contract — it buffers a TraceLine per request_id in memory, and only
appends the JSONL line once the trace is complete (outcome reported, or
timed out / errored). That's what keeps "one line per request" honest
instead of mutating an already-appended file.

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
    multiple worker processes — this app is explicitly single-user/local
    (PRD §7.4), so that's a documented non-goal, not an oversight.
    """

    def __init__(self, traces_file: Path = TRACES_FILE):
        self._traces_file = traces_file
        self._traces_file.parent.mkdir(parents=True, exist_ok=True)
        self._buffer: dict[str, TraceLine] = {}
        self._server_clock_start: dict[str, float] = {}
        self._lock = asyncio.Lock()

    # -- lifecycle -----------------------------------------------------

    def start(self, trace: TraceLine) -> None:
        """Register a new in-flight trace. Called from POST /requests."""
        self._buffer[trace.request_id] = trace
        self._server_clock_start[trace.request_id] = time.monotonic()

    def get(self, request_id: str) -> Optional[TraceLine]:
        return self._buffer.get(request_id)

    def mark_dispatch_complete(self, request_id: str) -> None:
        """Call the instant the provider call is actually fired."""
        trace = self._buffer.get(request_id)
        if trace is None:
            return
        start = self._server_clock_start.get(request_id)
        if start is not None and trace.latency:
            trace.latency.t_dispatch_ms = (time.monotonic() - start) * 1000

    def mark_stream_complete(
        self, request_id: str, tokens: Optional[TokenUsage] = None
    ) -> None:
        trace = self._buffer.get(request_id)
        if trace is None:
            return
        start = self._server_clock_start.get(request_id)
        dispatch_ms = trace.latency.t_dispatch_ms if trace.latency else None
        if start is not None:
            elapsed = (time.monotonic() - start) * 1000
            trace.latency.t_stream_ms = elapsed - (dispatch_ms or 0)
        if tokens is not None:
            trace.tokens = tokens

    async def finalize(
        self,
        request_id: str,
        outcome: Outcome,
        t_render_ms: Optional[float] = None,
        cost_usd: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> Optional[TraceLine]:
        """
        Completes and writes the trace line exactly once. Safe to call
        more than once for the same request_id (e.g. a cancel racing an
        outcome report) — only the first call actually writes.
        """
        async with self._lock:
            trace = self._buffer.pop(request_id, None)
            self._server_clock_start.pop(request_id, None)
            if trace is None:
                return None  # already finalized, or never started

            trace.outcome = outcome
            if t_render_ms is not None and trace.latency:
                trace.latency.t_render_ms = t_render_ms
            if cost_usd is not None:
                trace.cost_usd = cost_usd
            if error_message is not None:
                trace.error_message = error_message

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
