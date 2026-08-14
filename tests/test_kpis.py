import pytest

from kpis import (
    budget_compliance,
    compute_all_kpis,
    cost_per_accepted_draft,
    draft_acceptance_rate,
    wasted_token_ratio,
)


def make_trace(outcome, cost_usd=0.0, total_tokens=100, e2e_ms=None):
    return {
        "outcome": outcome,
        "cost_usd": cost_usd,
        "tokens": {"total_tokens": total_tokens},
        "latency": {"e2e_ms": e2e_ms} if e2e_ms is not None else {},
    }


# --- CPAD ---------------------------------------------------------------

def test_cpad_basic():
    traces = [
        make_trace("accepted", cost_usd=0.01),
        make_trace("accepted", cost_usd=0.02),
        make_trace("discarded", cost_usd=0.01),
    ]
    # total spend 0.04 / 2 accepted = 0.02
    assert cost_per_accepted_draft(traces) == pytest.approx(0.02)


def test_cpad_none_when_no_accepted():
    traces = [make_trace("discarded", cost_usd=0.01)]
    assert cost_per_accepted_draft(traces) is None


def test_cpad_empty_traces():
    assert cost_per_accepted_draft([]) is None


# --- DAR ------------------------------------------------------------------

def test_dar_basic():
    traces = [make_trace("accepted")] * 3 + [make_trace("discarded")] * 1
    assert draft_acceptance_rate(traces) == pytest.approx(0.75)


def test_dar_excludes_errors_and_timeouts_from_denominator():
    traces = [make_trace("accepted"), make_trace("error"), make_trace("timeout")]
    # only 1 accepted, 0 discarded -> 1/1 = 1.0, errors/timeouts don't count
    assert draft_acceptance_rate(traces) == pytest.approx(1.0)


def test_dar_none_when_nothing_returned():
    traces = [make_trace("error"), make_trace("timeout")]
    assert draft_acceptance_rate(traces) is None


# --- WTR --------------------------------------------------------------------

def test_wtr_basic():
    traces = [
        make_trace("accepted", total_tokens=100),
        make_trace("discarded", total_tokens=50),
        make_trace("superseded", total_tokens=25),
    ]
    # wasted = 50+25=75, total = 175 -> 75/175
    assert wasted_token_ratio(traces) == pytest.approx(75 / 175)


def test_wtr_all_wasted_outcomes_counted():
    traces = [make_trace(o, total_tokens=10) for o in
              ["discarded", "cancelled", "superseded", "timeout", "error"]]
    assert wasted_token_ratio(traces) == pytest.approx(1.0)


def test_wtr_none_accepted_only_zero():
    traces = [make_trace("accepted", total_tokens=100)]
    assert wasted_token_ratio(traces) == pytest.approx(0.0)


def test_wtr_none_when_no_tokens_at_all():
    traces = [make_trace("accepted", total_tokens=0)]
    assert wasted_token_ratio(traces) is None


def test_wtr_falls_back_to_summing_parts_when_total_missing():
    trace = {
        "outcome": "discarded",
        "tokens": {"input_text_tokens": 10, "input_image_tokens": 20, "output_tokens": 5},
    }
    accepted = {
        "outcome": "accepted",
        "tokens": {"input_text_tokens": 10, "output_tokens": 10},
    }
    ratio = wasted_token_ratio([trace, accepted])
    # wasted = 35, total = 35+20 = 55
    assert ratio == pytest.approx(35 / 55)


# --- BC -----------------------------------------------------------------------

def test_bc_basic():
    traces = [
        make_trace("accepted", e2e_ms=1000),
        make_trace("accepted", e2e_ms=9000),  # over an 8000ms budget
        make_trace("accepted", e2e_ms=4000),
    ]
    assert budget_compliance(traces, budget_ms=8000) == pytest.approx(2 / 3)


def test_bc_exactly_at_budget_counts_as_compliant():
    traces = [make_trace("accepted", e2e_ms=8000)]
    assert budget_compliance(traces, budget_ms=8000) == pytest.approx(1.0)


def test_bc_ignores_traces_with_no_e2e_recorded():
    traces = [make_trace("error", e2e_ms=None), make_trace("accepted", e2e_ms=1000)]
    assert budget_compliance(traces, budget_ms=8000) == pytest.approx(1.0)


def test_bc_none_when_nothing_measured():
    traces = [make_trace("error", e2e_ms=None)]
    assert budget_compliance(traces) is None


# --- compute_all_kpis --------------------------------------------------------

def test_compute_all_kpis_returns_summary_with_all_four():
    traces = [
        make_trace("accepted", cost_usd=0.01, total_tokens=100, e2e_ms=1000),
        make_trace("discarded", cost_usd=0.01, total_tokens=50, e2e_ms=2000),
    ]
    summary = compute_all_kpis(traces, budget_ms=8000)
    d = summary.as_dict()
    assert d["cpad_usd"] == pytest.approx(0.02)
    assert d["dar"] == pytest.approx(0.5)
    assert d["wtr"] == pytest.approx(round(50 / 150, 4))
    assert d["bc"] == pytest.approx(1.0)
    assert d["budget_ms"] == 8000


def test_compute_all_kpis_handles_empty_traces_without_crashing():
    summary = compute_all_kpis([])
    d = summary.as_dict()
    assert d["cpad_usd"] is None
    assert d["dar"] is None
    assert d["wtr"] is None
    assert d["bc"] is None
