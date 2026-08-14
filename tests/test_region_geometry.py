import pytest

import router
from models import BoundingBox, Provider, RegionContext, Tier
from router import RoutingThresholds, decide


def make_context(width=512, height=512, stroke_count=5, ink_density=0.1) -> RegionContext:
    return RegionContext(
        bbox=BoundingBox(x=0, y=0, width=width, height=height),
        zoom=1.0,
        source="ink_cluster",
        stroke_count=stroke_count,
        ink_density=ink_density,
    )


@pytest.fixture(autouse=True)
def _disable_real_gemini_quota(monkeypatch):
    """Routing tests should not depend on today's real experiment usage."""
    monkeypatch.setattr(router, "check_gemini_quota", lambda: None)

def test_small_sparse_region_routes_fast():
    ctx = make_context(width=256, height=256, stroke_count=3, ink_density=0.05)
    decision = decide(ctx)
    assert decision.tier == Tier.fast
    assert decision.provider == Provider.ollama


def test_dense_diagram_like_region_routes_heavy():
    # High stroke count + high density + not text-like (density too high to
    # pass the text heuristic's own density check consistently used here)
    ctx = make_context(width=900, height=900, stroke_count=60, ink_density=0.6)
    decision = decide(ctx)
    assert decision.tier == Tier.heavy
    assert decision.provider == Provider.gemini


def test_large_bbox_alone_routes_heavy():
    ctx = make_context(width=1500, height=1500, stroke_count=5, ink_density=0.05)
    decision = decide(ctx)
    assert decision.tier == Tier.heavy


def test_text_like_signal_overrides_stroke_count():
    # Many short strokes at moderate density = text signal, should route
    # fast even though stroke_count alone exceeds the threshold.
    thresholds = RoutingThresholds(max_fast_stroke_count=10)
    ctx = make_context(width=512, height=512, stroke_count=20, ink_density=0.2)
    decision = decide(ctx, thresholds=thresholds)
    assert decision.tier == Tier.fast
    assert "text-like" in decision.reason

def test_provider_override_bypasses_heuristic_entirely(monkeypatch):
    monkeypatch.setattr(router, "check_gemini_quota", lambda: None)

    ctx = make_context(width=2000, height=2000, stroke_count=200, ink_density=0.9)

    decision = decide(ctx, provider_override=Provider.gemini)
    assert decision.provider == Provider.gemini
    assert "pinned" in decision.reason

    decision2 = decide(ctx, provider_override=Provider.ollama)
    assert decision2.provider == Provider.ollama
    assert decision2.tier == Tier.fast

def test_routing_reason_is_never_empty():
    ctx = make_context()
    decision = decide(ctx)
    assert decision.reason
