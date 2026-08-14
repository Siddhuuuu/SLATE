import pytest

from cost import compute_cost_usd

TEST_RATES = {
    "test-model": {
        "input_per_million": 1.0,
        "output_per_million": 2.0,
    },
    "free-model": {
        "input_per_million": 0.0,
        "output_per_million": 0.0,
    },
}


def test_basic_cost_calculation():
    # (in * rate_in + out * rate_out) / 1e6, per the brief's formula
    cost = compute_cost_usd(
        model="test-model",
        input_text_tokens=1_000_000,
        output_tokens=1_000_000,
        rates=TEST_RATES,
    )
    assert cost == pytest.approx(3.0)


def test_input_image_and_text_combine_at_the_same_input_rate():
    # The brief's formula gives image tokens no separate rate — they're
    # billed at rate_in exactly like text tokens.
    cost = compute_cost_usd(
        model="test-model",
        input_text_tokens=500_000,
        input_image_tokens=500_000,
        rates=TEST_RATES,
    )
    assert cost == pytest.approx(1.0)  # 1,000,000 combined input tokens * 1.0/million


def test_reasoning_tokens_billed_at_output_rate():
    # Per the brief: "(in x rate_in + out x rate_out + reasoning x rate_out)"
    cost = compute_cost_usd(
        model="test-model",
        output_tokens=0,
        reasoning_tokens=1_000_000,
        rates=TEST_RATES,
    )
    assert cost == pytest.approx(2.0)  # reasoning billed at output rate (2.0/million)


def test_zero_rate_model_is_free():
    cost = compute_cost_usd(
        model="free-model",
        input_text_tokens=999_999,
        input_image_tokens=999_999,
        output_tokens=999_999,
        reasoning_tokens=999_999,
        rates=TEST_RATES,
    )
    assert cost == 0.0


def test_all_none_token_counts_treated_as_zero():
    cost = compute_cost_usd(model="test-model", rates=TEST_RATES)
    assert cost == 0.0


def test_unknown_model_raises():
    with pytest.raises(KeyError):
        compute_cost_usd(model="nonexistent-model", input_text_tokens=100, rates=TEST_RATES)


def test_partial_tokens():
    cost = compute_cost_usd(
        model="test-model", input_text_tokens=500_000, rates=TEST_RATES
    )
    assert cost == pytest.approx(0.5)


def test_default_rates_file_loads_and_has_known_models():
    # Sanity check against the real config/rates.yaml, not the test fixture.
    cost = compute_cost_usd(model="gemini-3.6-flash", input_text_tokens=1000, output_tokens=1000)
    assert cost >= 0.0

    cost_local = compute_cost_usd(
        model="qwen3-vl:4b-instruct", input_text_tokens=100_000, output_tokens=100_000
    )
    assert cost_local == 0.0


def test_full_formula_matches_brief_example():
    # Reproduces the brief's own example trace line's cost as a sanity
    # cross-check of the formula shape (not the exact input/output split,
    # which the example doesn't fully specify token-by-token).
    rates = {"claude-sonnet-4-5": {"input_per_million": 3.0, "output_per_million": 15.0}}
    cost = compute_cost_usd(
        model="claude-sonnet-4-5",
        input_text_tokens=214,
        input_image_tokens=1105,
        output_tokens=388,
        reasoning_tokens=1024,
        rates=rates,
    )
    expected = (1319 * 3.0 + (388 + 1024) * 15.0) / 1_000_000
    assert cost == pytest.approx(expected)
