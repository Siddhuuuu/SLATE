"""
quota_guard.py — a hard, conservative safety cap on Gemini free-tier usage.

Published free-tier numbers (RPD especially) vary wildly across Google's
own docs, third-party trackers, and blog posts — and Google explicitly
states limits are assigned per-project, not published as one universal
table. The only number that means anything is whatever YOUR account's
AI Studio dashboard shows, right now.

DEFAULT_MAX_PER_DAY defaults to 15, deliberately below the ~20 RPD this
project's dashboard showed at setup time — so a slightly-wrong assumption
about the exact quota is safe to be wrong in (under-uses it), never
unsafe (over-uses it). Raise GEMINI_MAX_REQUESTS_PER_DAY in .env once
you've confirmed your own dashboard's real number and want more headroom.

Known limitation: the daily count is read from *completed* (finalized)
traces in traces.jsonl, so a burst of requests fired faster than they
finalize could momentarily undercount. Normal human-paced drawing doesn't
hit this; a script firing many Gemini calls back-to-back could. The
per-minute check below exists specifically to catch that case too.
"""
from __future__ import annotations

import os
import time
from collections import deque
from datetime import datetime, timezone

from tracer import tracer

DEFAULT_MAX_PER_DAY = int(os.environ.get("GEMINI_MAX_REQUESTS_PER_DAY", "15"))
DEFAULT_MAX_PER_MINUTE = int(os.environ.get("GEMINI_MAX_REQUESTS_PER_MINUTE", "4"))

# In-memory sliding window of the last 60s of Gemini calls actually fired
# by this process. Resets on restart — a known, accepted gap (see above).
_minute_window: deque[float] = deque()


class QuotaExceeded(Exception):
    """Raised when firing a Gemini request right now would risk breaching
    the daily or per-minute safety cap. Callers decide what to do with
    it — router.py downgrades gracefully for auto-routed requests, but
    re-raises for pinned experiment-harness requests (see router.py)."""


def _today_utc_date_str() -> str:
    # Google resets RPD at midnight Pacific, not UTC. Using UTC's date
    # boundary means this can reset up to ~8 hours early relative to
    # Pacific midnight — the safe direction to be wrong in, since it only
    # makes the cap MORE conservative, never less.
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _count_gemini_requests_today() -> int:
    today = _today_utc_date_str()
    count = 0
    for trace in tracer.read_all_completed():
        if trace.get("provider") == "gemini" and str(trace.get("created_at", "")).startswith(today):
            count += 1
    return count


def check_gemini_quota(
    max_per_day: int = DEFAULT_MAX_PER_DAY, max_per_minute: int = DEFAULT_MAX_PER_MINUTE
) -> None:
    """Call BEFORE committing to a Gemini call. Raises QuotaExceeded if
    either cap would be breached; does nothing (and books no usage) if
    the call is safe to make. Call record_gemini_request() separately,
    only once the call is actually about to fire."""
    now = time.time()
    while _minute_window and now - _minute_window[0] > 60:
        _minute_window.popleft()
    if len(_minute_window) >= max_per_minute:
        raise QuotaExceeded(f"Gemini per-minute safety cap reached ({max_per_minute}/min)")

    today_count = _count_gemini_requests_today()
    if today_count >= max_per_day:
        raise QuotaExceeded(f"Gemini daily safety cap reached ({today_count}/{max_per_day} today, UTC)")


def record_gemini_request() -> None:
    """Call once a Gemini request is actually being dispatched (not just
    checked) — books it against the per-minute window."""
    _minute_window.append(time.time())