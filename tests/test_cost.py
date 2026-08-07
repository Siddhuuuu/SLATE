import pytest

from cost import compute_cost_usd

TEST_RATES = {
    "test-model": {
        "input_per_million": 1.0,
        "output_per_million": 2.0,
        "image_per_million": 0.5,
    },
    "free-model": {
        "input_per_million": 0.0,
        "output_per_million": 0.0,
        "image_per_million": 0.0,
    },
}


def test_basic_cost_calculation():
    cost = compute_cost_usd(
        model="test-model",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        image_tokens=0,
        rates=TEST_RATES,
    )
    assert cost == pytest.approx(3.0)


def test_image_tokens_included():
    cost = compute_cost_usd(
        model="test-model",
        input_tokens=0,
        output_tokens=0,
        image_tokens=1_000_000,
        rates=TEST_RATES,
    )
    assert cost == pytest.approx(0.5)


def test_zero_rate_model_is_free():
    cost = compute_cost_usd(
        model="free-model",
        input_tokens=999_999,
        output_tokens=999_999,
        image_tokens=999_999,
        rates=TEST_RATES,
    )
    assert cost == 0.0


def test_none_token_counts_treated_as_zero():
    cost = compute_cost_usd(
        model="test-model", input_tokens=None, output_tokens=None, image_tokens=None, rates=TEST_RATES
    )
    assert cost == 0.0


def test_unknown_model_raises():
    with pytest.raises(KeyError):
        compute_cost_usd(
            model="nonexistent-model", input_tokens=100, output_tokens=100, rates=TEST_RATES
        )


def test_partial_tokens():
    cost = compute_cost_usd(
        model="test-model", input_tokens=500_000, output_tokens=None, rates=TEST_RATES
    )
    assert cost == pytest.approx(0.5)


def test_default_rates_file_loads_and_has_known_models():
    # Sanity check against the real config/rates.yaml, not the test fixture.
    cost = compute_cost_usd(model="gemini-3-flash", input_tokens=1000, output_tokens=1000)
    assert cost >= 0.0

    cost_local = compute_cost_usd(model="qwen3-vl:4b", input_tokens=100_000, output_tokens=100_000)
    assert cost_local == 0.0
