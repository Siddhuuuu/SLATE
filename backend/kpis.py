"""
kpis.py — the four required derived KPIs (brief Section 5, B3), computed
as pure functions over a list of trace dicts (the same shape tracer.py's
read_all_completed() returns — one dict per completed trace line).

Kept pure and dependency-free (no tracer.py import) so these are testable
against plain fixtures, and reusable from both main.py's live panel
endpoint and scripts/analyze_traces.py's REPORT.md generation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Outcomes counted as "wasted" for WTR — tokens spent that never became
# something the user kept. Matches the brief's list exactly.
WASTED_OUTCOMES = {"discarded", "cancelled", "superseded", "timeout", "error"}

# Declared latency budget for BC (Budget Compliance) — p95 e2e target
# stated in README.md. THESE TWO MUST STAY IN SYNC; this is the single
# source of truth the README's number should quote, not the reverse.
DEFAULT_LATENCY_BUDGET_MS = 8000


def _trace_total_tokens(trace: dict) -> int:
    tokens = trace.get("tokens") or {}
    total = tokens.get("total_tokens")
    if total is not None:
        return total
    # Fall back to summing parts if total_tokens itself wasn't recorded
    # (e.g. an error before any usage object ever arrived).
    parts = [
        tokens.get("input_text_tokens"),
        tokens.get("input_image_tokens"),
        tokens.get("output_tokens"),
        tokens.get("reasoning_tokens"),
    ]
    known = [p for p in parts if p is not None]
    return sum(known) if known else 0


def cost_per_accepted_draft(traces: list[dict]) -> Optional[float]:
    """CPAD = total spend / drafts accepted. None (not 0 or inf) when
    there are zero accepted drafts — a $/0 rate is undefined."""
    accepted = [t for t in traces if t.get("outcome") == "accepted"]
    if not accepted:
        return None
    total_cost = sum(t.get("cost_usd") or 0.0 for t in traces)
    return total_cost / len(accepted)


def draft_acceptance_rate(traces: list[dict]) -> Optional[float]:
    """DAR = accepted / (accepted + discarded). "Drafts returned" is read
    as drafts that actually reached the user and were explicitly decided
    on — not ones that errored, timed out, or got superseded before a
    person ever had the chance to judge them."""
    accepted = sum(1 for t in traces if t.get("outcome") == "accepted")
    discarded = sum(1 for t in traces if t.get("outcome") == "discarded")
    returned = accepted + discarded
    if returned == 0:
        return None
    return accepted / returned


def wasted_token_ratio(traces: list[dict]) -> Optional[float]:
    """WTR = tokens spent on discarded/cancelled/superseded/timeout/error
    requests / tokens spent on ALL requests."""
    if not traces:
        return None
    total_tokens = sum(_trace_total_tokens(t) for t in traces)
    if total_tokens == 0:
        return None
    wasted_tokens = sum(
        _trace_total_tokens(t) for t in traces if t.get("outcome") in WASTED_OUTCOMES
    )
    return wasted_tokens / total_tokens


def budget_compliance(
    traces: list[dict], budget_ms: float = DEFAULT_LATENCY_BUDGET_MS
) -> Optional[float]:
    """BC = share of requests whose e2e latency met the declared budget.
    Only counts requests where e2e_ms was actually recorded — a request
    that errored before ever streaming has nothing to compare against
    the budget, so it's excluded rather than counted as a failure."""
    known = [
        t["latency"]["e2e_ms"]
        for t in traces
        if t.get("latency") and t["latency"].get("e2e_ms") is not None
    ]
    if not known:
        return None
    compliant = sum(1 for e2e in known if e2e <= budget_ms)
    return compliant / len(known)


@dataclass
class KpiSummary:
    cpad_usd: Optional[float]
    dar: Optional[float]
    wtr: Optional[float]
    bc: Optional[float]
    budget_ms: float

    def as_dict(self) -> dict:
        return {
            "cpad_usd": round(self.cpad_usd, 6) if self.cpad_usd is not None else None,
            "dar": round(self.dar, 4) if self.dar is not None else None,
            "wtr": round(self.wtr, 4) if self.wtr is not None else None,
            "bc": round(self.bc, 4) if self.bc is not None else None,
            "budget_ms": self.budget_ms,
        }


def compute_all_kpis(traces: list[dict], budget_ms: float = DEFAULT_LATENCY_BUDGET_MS) -> KpiSummary:
    return KpiSummary(
        cpad_usd=cost_per_accepted_draft(traces),
        dar=draft_acceptance_rate(traces),
        wtr=wasted_token_ratio(traces),
        bc=budget_compliance(traces, budget_ms=budget_ms),
        budget_ms=budget_ms,
    )
