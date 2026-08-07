"""
estimator.py — image token estimator + MAE validation.

Pure functions, no I/O. This is the piece PRD §8 calls out as the closest
thing in this project to real ML: a small predictive function, validated
against ground truth, with a reported error bar.

IMPORTANT: the tiling formula below is a generic, documented placeholder
(a common square-tile scheme many vision APIs use as of early 2025-2026).
Per PRD §3/§8: verify the *current* formula against the live provider docs
before trusting this for anything that ends up in METRICS.md. Providers
change tiling rules across model versions without much fanfare.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class TilingRule:
    """Parameters of a square-tile image-token scheme."""
    tile_px: int = 768          # side length of one tile, pixels
    tokens_per_tile: int = 258  # tokens billed per tile
    base_tokens: int = 0        # flat overhead per image, if the provider charges one


DEFAULT_RULE = TilingRule()


def estimate_image_tokens(
    width_px: int,
    height_px: int,
    rule: TilingRule = DEFAULT_RULE,
) -> int:
    """
    Estimate billed image tokens from raw pixel dimensions using a square-
    tile scheme: the image is conceptually cut into `tile_px` x `tile_px`
    tiles (partial tiles at the edges still count as a full tile), and each
    tile costs `tokens_per_tile`.

        tiles = ceil(width / tile_px) * ceil(height / tile_px)
        tokens = base_tokens + tiles * tokens_per_tile

    This is a *documented estimate*, not a guarantee — see module docstring.
    """
    if width_px <= 0 or height_px <= 0:
        raise ValueError("width_px and height_px must be positive")

    tiles_w = math.ceil(width_px / rule.tile_px)
    tiles_h = math.ceil(height_px / rule.tile_px)
    return rule.base_tokens + tiles_w * tiles_h * rule.tokens_per_tile


def mean_absolute_error(predictions: list[float], ground_truth: list[float]) -> float:
    """
    Pure MAE. Raises on length mismatch or an empty input rather than
    silently returning 0 — an empty validation set is not a valid MAE,
    it's a missing one, and PRD §8 requires >=20 real requests.
    """
    if len(predictions) != len(ground_truth):
        raise ValueError(
            f"predictions ({len(predictions)}) and ground_truth "
            f"({len(ground_truth)}) must be the same length"
        )
    if len(predictions) == 0:
        raise ValueError("cannot compute MAE over an empty validation set")

    errors = [abs(p - g) for p, g in zip(predictions, ground_truth)]
    return sum(errors) / len(errors)


@dataclass
class ValidationResult:
    n: int
    mae: float
    mean_ground_truth: float
    mae_as_pct_of_mean: float

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "mae": round(self.mae, 3),
            "mean_ground_truth": round(self.mean_ground_truth, 3),
            "mae_as_pct_of_mean": round(self.mae_as_pct_of_mean, 2),
        }


def validate(predictions: list[float], ground_truth: list[float]) -> ValidationResult:
    """
    Wraps mean_absolute_error with the extra context METRICS.md actually
    wants to report: n (so a small validation set can't hide behind a
    good-looking MAE) and MAE as a percentage of the mean ground truth
    (an absolute error is meaningless without a sense of scale).

    PRD §8 requires n >= 20 real requests before this number goes in a
    report — that floor is enforced by the caller (scripts/analyze_traces.py
    or a validation notebook), not here, so this function stays reusable
    for smaller ad-hoc checks during development too.
    """
    mae = mean_absolute_error(predictions, ground_truth)
    mean_gt = sum(ground_truth) / len(ground_truth)
    pct = (mae / mean_gt * 100) if mean_gt else float("inf")
    return ValidationResult(
        n=len(predictions), mae=mae, mean_ground_truth=mean_gt, mae_as_pct_of_mean=pct
    )
