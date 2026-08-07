"""
router.py — the shipped feature from PRD §10.

A threshold-based heuristic, deliberately not a trained classifier (see
PRD §1 — no fine-tuning, and this problem doesn't need one). It looks at
cheap, already-available signals from the captured region and decides
between a fast/local tier and a heavier/cloud tier.

Every threshold here is a documented guess, not a tuned constant — that's
fine and expected for a v1 heuristic, but write your reasoning in IDEAS.md
next to the `model_dependency` / `risk` fields the template asks for, and
revisit these numbers once real trace data exists.
"""
from __future__ import annotations

from dataclasses import dataclass

from models import Provider, RegionContext, Tier
from adapters.client import PROVIDER_CONFIG


@dataclass(frozen=True)
class RoutingThresholds:
    """Tune these against real trace data once you have some — see PRD §9."""
    max_fast_stroke_count: int = 40      # more strokes than this -> likely a dense/complex region
    max_fast_ink_density: float = 0.35   # strokes per unit area; above this -> crowded region
    max_fast_bbox_area_frac: float = 0.5 # bbox as a fraction of a "typical" region size
    text_signal_favors_fast: bool = True # simple text-like strokes route fast even if numerous


@dataclass(frozen=True)
class RoutingDecision:
    tier: Tier
    provider: Provider
    model: str
    reason: str


DEFAULT_THRESHOLDS = RoutingThresholds()

# Reference bbox area (px^2) used to normalize max_fast_bbox_area_frac —
# roughly a 1024x1024 capped crop per PRD §6.
_REFERENCE_BBOX_AREA = 1024 * 1024


def _looks_like_text(context: RegionContext) -> bool:
    """
    Crude text-vs-diagram signal: text tends to produce many short strokes
    packed at moderate density; diagrams/equations tend to produce fewer,
    longer, more varied strokes. This is intentionally simple (PRD §10
    explicitly scopes out anything fancier) — a real classifier is future
    work, not a v1 requirement.
    """
    if context.stroke_count == 0:
        return False
    avg_density = context.ink_density
    # Text sits in a moderate density band: dense enough to be more than a
    # few scattered marks, but not so dense it's more likely a packed
    # diagram or scribble. The upper bound is what keeps this from
    # rubber-stamping every crowded region as "text" regardless of shape.
    return 0.15 < avg_density <= 0.45 and context.stroke_count >= 8


def decide(
    context: RegionContext,
    thresholds: RoutingThresholds = DEFAULT_THRESHOLDS,
    provider_override: Provider | None = None,
) -> RoutingDecision:
    """
    Returns which tier/provider/model to call for this request.

    `provider_override` exists for exactly one caller: the B5 experiment
    harness, which pins an arm to a specific provider and must bypass the
    heuristic entirely (PRD §3 — arms must be pinned, never auto-routed,
    or a rate-limit fallback silently contaminates the data).
    """
    if provider_override is not None:
        cfg = PROVIDER_CONFIG[provider_override.value]
        return RoutingDecision(
            tier=Tier.heavy if provider_override != Provider.ollama else Tier.fast,
            provider=provider_override,
            model=cfg["model"],
            reason=f"provider pinned by caller (experiment harness): {provider_override.value}",
        )

    bbox_area = max(context.bbox.width * context.bbox.height, 1.0)
    area_frac = bbox_area / _REFERENCE_BBOX_AREA

    reasons: list[str] = []
    route_fast = True

    if context.stroke_count > thresholds.max_fast_stroke_count:
        route_fast = False
        reasons.append(f"stroke_count {context.stroke_count} > {thresholds.max_fast_stroke_count}")

    if context.ink_density > thresholds.max_fast_ink_density:
        route_fast = False
        reasons.append(f"ink_density {context.ink_density:.2f} > {thresholds.max_fast_ink_density}")

    if area_frac > thresholds.max_fast_bbox_area_frac:
        route_fast = False
        reasons.append(f"region area {area_frac:.2f}x reference > {thresholds.max_fast_bbox_area_frac}x")

    if not route_fast and thresholds.text_signal_favors_fast and _looks_like_text(context):
        route_fast = True
        reasons.append("overridden: text-like signal detected, routing fast despite density/count")

    if route_fast:
        cfg = PROVIDER_CONFIG["ollama"]
        return RoutingDecision(
            tier=Tier.fast,
            provider=Provider.ollama,
            model=cfg["model"],
            reason="within fast-tier thresholds" if not reasons else "; ".join(reasons),
        )

    cfg = PROVIDER_CONFIG["gemini"]
    return RoutingDecision(
        tier=Tier.heavy,
        provider=Provider.gemini,
        model=cfg["model"],
        reason="; ".join(reasons) or "exceeded fast-tier thresholds",
    )
