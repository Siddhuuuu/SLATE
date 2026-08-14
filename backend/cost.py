"""
cost.py — pure functions only. No network, no filesystem inside the
compute path (rates are loaded once and passed in), so this is trivially
unit-testable per PRD §7.3.

Formula matches the assignment brief EXACTLY (Section 5, B2):
    cost = (in * rate_in + out * rate_out + reasoning * rate_out) / 1,000,000

Where "in" is input_text_tokens + input_image_tokens combined at ONE
input rate (the brief's formula does not give image tokens a separate
rate), and reasoning tokens are billed at the OUTPUT rate — the brief
states this explicitly ("many providers bill hidden thinking tokens as
output"), which also matches what was found empirically in this
project's own traces (Gemini's total_tokens included ~198 tokens not
reflected in input+output, consistent with reasoning tokens billed
alongside output).
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
    input_text_tokens: Optional[int] = None,
    input_image_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    reasoning_tokens: Optional[int] = None,
    rates: Optional[dict] = None,
) -> float:
    """
    Pure function: tokens + rate table -> cost in USD, using the brief's
    exact formula: (in * rate_in + out * rate_out + reasoning * rate_out) / 1e6

    Unknown/None token counts are treated as zero contribution rather than
    raising — a partial trace (e.g. a mid-stream error/timeout) should
    still cost something computable, not crash the tracer.

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
    rate_in = row.get("input_per_million", 0.0)
    rate_out = row.get("output_per_million", 0.0)

    in_tok = (input_text_tokens or 0) + (input_image_tokens or 0)
    out_tok = output_tokens or 0
    reasoning_tok = reasoning_tokens or 0

    cost = (in_tok * rate_in + out_tok * rate_out + reasoning_tok * rate_out) / 1_000_000
    return round(cost, 8)
