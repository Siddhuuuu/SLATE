import pytest

from estimator import (
    TilingRule,
    estimate_image_tokens,
    mean_absolute_error,
    validate,
)


def test_single_tile_image():
    rule = TilingRule(tile_px=768, tokens_per_tile=258, base_tokens=0)
    # exactly one tile
    assert estimate_image_tokens(768, 768, rule=rule) == 258


def test_partial_tile_rounds_up():
    rule = TilingRule(tile_px=768, tokens_per_tile=258, base_tokens=0)
    # 769px wide -> needs 2 tiles wide even though it barely crosses the boundary
    tokens = estimate_image_tokens(769, 768, rule=rule)
    assert tokens == 2 * 258


def test_base_tokens_added():
    rule = TilingRule(tile_px=768, tokens_per_tile=258, base_tokens=85)
    tokens = estimate_image_tokens(768, 768, rule=rule)
    assert tokens == 258 + 85


def test_capped_1024_crop_is_two_by_two_tiles_at_default_rule():
    # PRD §6: crops are capped at 1024px long edge. At the default 768px
    # tile size, a 1024x1024 crop needs 2x2 = 4 tiles.
    tokens = estimate_image_tokens(1024, 1024)
    assert tokens == 4 * 258


def test_invalid_dimensions_raise():
    with pytest.raises(ValueError):
        estimate_image_tokens(0, 100)
    with pytest.raises(ValueError):
        estimate_image_tokens(100, -5)


def test_mae_perfect_predictions():
    assert mean_absolute_error([100, 200, 300], [100, 200, 300]) == 0.0


def test_mae_known_value():
    # errors: 10, 20, 30 -> mean 20
    mae = mean_absolute_error([110, 220, 330], [100, 200, 300])
    assert mae == pytest.approx(20.0)


def test_mae_length_mismatch_raises():
    with pytest.raises(ValueError):
        mean_absolute_error([1, 2, 3], [1, 2])


def test_mae_empty_input_raises():
    with pytest.raises(ValueError):
        mean_absolute_error([], [])


def test_validate_reports_n_and_pct():
    result = validate([110, 220, 330], [100, 200, 300])
    d = result.as_dict()
    assert d["n"] == 3
    assert d["mae"] == pytest.approx(20.0)
    assert d["mean_ground_truth"] == pytest.approx(200.0)
    assert d["mae_as_pct_of_mean"] == pytest.approx(10.0)
