"""
cost.py — pure functions only. No network, no filesystem inside the
compute path (rates are loaded once and passed in), so this is trivially
unit-testable per PRD §7.3.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

RATES_PATH = Path(__file__).parent / "config" / "rates.yaml"


@lru_cache(maxsize=1)
def load_rates(path: Path = RATES_PATH) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def compute_cost_usd(
    model: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    image_tokens: Optional[int] = None,
    rates: Optional[dict] = None,
) -> float:
    """
    Pure function: tokens + rate table -> cost in USD.

    Unknown/None token counts are treated as zero contribution rather than
    raising — a partial trace (e.g. a mid-stream error) should still cost
    something computable, not crash the tracer.

    Raises KeyError if `model` has no entry in the rate table — silently
    defaulting to $0 for an unknown model would corrupt the report, and
    that's worse than a loud failure at write time.
    """
    table = rates if rates is not None else load_rates()
    if model not in table:
        raise KeyError(
            f"No rate entry for model '{model}' in rates.yaml — "
            f"add one before this model can appear in a trace."
        )

    row = table[model]
    in_tok = input_tokens or 0
    out_tok = output_tokens or 0
    img_tok = image_tokens or 0

    cost = (
        in_tok * row.get("input_per_million", 0.0) / 1_000_000
        + out_tok * row.get("output_per_million", 0.0) / 1_000_000
        + img_tok * row.get("image_per_million", 0.0) / 1_000_000
    )
    return round(cost, 8)
