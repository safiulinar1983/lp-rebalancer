from decimal import Decimal

import pytest

from blockchain.liquidity_math import (
    Q96,
    amounts_per_liquidity,
    estimate_swap_to_balance,
    sqrt_ratio_at_tick,
)


def test_price_below_range_requires_only_token0():
    amounts = amounts_per_liquidity(
        sqrt_ratio_at_tick(100),
        200,
        400,
    )

    assert amounts.amount0 > 0
    assert amounts.amount1 == 0


def test_price_inside_range_requires_both_tokens():
    amounts = amounts_per_liquidity(
        sqrt_ratio_at_tick(300),
        200,
        400,
    )

    assert amounts.amount0 > 0
    assert amounts.amount1 > 0


def test_price_above_range_requires_only_token1():
    amounts = amounts_per_liquidity(
        sqrt_ratio_at_tick(500),
        200,
        400,
    )

    assert amounts.amount0 == 0
    assert amounts.amount1 > 0


def test_invalid_tick_is_rejected():
    with pytest.raises(ValueError, match="Tick outside"):
        sqrt_ratio_at_tick(887273)


def test_invalid_range_is_rejected():
    with pytest.raises(ValueError, match="lower_tick"):
        amounts_per_liquidity(
            Decimal("1"),
            200,
            200,
        )


def test_negative_balance_is_rejected():
    with pytest.raises(ValueError, match="cannot be negative"):
        estimate_swap_to_balance(
            -1,
            100,
            int(Q96),
            -100,
            100,
        )


def test_zero_sqrt_price_is_rejected():
    with pytest.raises(ValueError, match="must be positive"):
        estimate_swap_to_balance(
            100,
            100,
            0,
            -100,
            100,
        )


def test_swap_from_token0_when_token0_is_in_surplus():
    estimate = estimate_swap_to_balance(
        balance0=1_000_000,
        balance1=1,
        sqrt_price_x96=int(Q96),
        lower_tick=-100,
        upper_tick=100,
    )

    assert estimate is not None
    assert estimate.token_in == 0
    assert estimate.amount_in > 0
    assert estimate.expected_amount_out > 0


def test_swap_from_token1_when_token1_is_in_surplus():
    estimate = estimate_swap_to_balance(
        balance0=1,
        balance1=1_000_000,
        sqrt_price_x96=int(Q96),
        lower_tick=-100,
        upper_tick=100,
    )

    assert estimate is not None
    assert estimate.token_in == 1
    assert estimate.amount_in > 0
    assert estimate.expected_amount_out > 0


def test_no_swap_when_balances_match_required_ratio():
    sqrt_price_x96 = int(Q96)
    lower_tick = -100
    upper_tick = 100

    amounts = amounts_per_liquidity(
        Decimal(sqrt_price_x96) / Q96,
        lower_tick,
        upper_tick,
    )

    # Use a large integer approximation of the required ratio.
    scale = Decimal(10**12)
    balance0 = int(amounts.amount0 * scale)
    balance1 = int(amounts.amount1 * scale)

    estimate = estimate_swap_to_balance(
        balance0,
        balance1,
        sqrt_price_x96,
        lower_tick,
        upper_tick,
    )

    assert estimate is None or estimate.amount_in < Decimal("1")


def test_sqrt_ratio_at_tick_zero_is_one():
    assert sqrt_ratio_at_tick(0) == Decimal("1")


def test_swap_from_token0_produces_required_token_ratio():
    balance0 = 1_000_000
    balance1 = 1
    sqrt_price_x96 = int(Q96)
    lower_tick = -100
    upper_tick = 100

    estimate = estimate_swap_to_balance(
        balance0, balance1, sqrt_price_x96, lower_tick, upper_tick
    )
    assert estimate is not None
    assert estimate.token_in == 0

    amounts = amounts_per_liquidity(
        Decimal(sqrt_price_x96) / Q96, lower_tick, upper_tick
    )
    target_ratio = amounts.amount0 / amounts.amount1
    remaining0 = Decimal(balance0) - estimate.amount_in
    remaining1 = Decimal(balance1) + estimate.expected_amount_out
    actual_ratio = remaining0 / remaining1

    assert abs(actual_ratio - target_ratio) / target_ratio < Decimal("1e-10")


def test_swap_from_token1_produces_required_token_ratio():
    balance0 = 1
    balance1 = 1_000_000
    sqrt_price_x96 = int(Q96)
    lower_tick = -100
    upper_tick = 100

    estimate = estimate_swap_to_balance(
        balance0, balance1, sqrt_price_x96, lower_tick, upper_tick
    )
    assert estimate is not None
    assert estimate.token_in == 1

    amounts = amounts_per_liquidity(
        Decimal(sqrt_price_x96) / Q96, lower_tick, upper_tick
    )
    target_ratio = amounts.amount0 / amounts.amount1
    remaining0 = Decimal(balance0) + estimate.expected_amount_out
    remaining1 = Decimal(balance1) - estimate.amount_in
    actual_ratio = remaining0 / remaining1

    assert abs(actual_ratio - target_ratio) / target_ratio < Decimal("1e-10")


def test_above_range_swaps_all_token0_when_only_token1_is_required():
    price = int(sqrt_ratio_at_tick(200) * Q96)

    estimate = estimate_swap_to_balance(
        balance0=1000,
        balance1=500,
        sqrt_price_x96=price,
        lower_tick=-100,
        upper_tick=100,
    )

    assert estimate is not None
    assert estimate.token_in == 0
    assert estimate.amount_in == Decimal(1000)


def test_above_range_needs_no_swap_when_token0_balance_is_zero():
    price = int(sqrt_ratio_at_tick(200) * Q96)

    estimate = estimate_swap_to_balance(
        balance0=0,
        balance1=500,
        sqrt_price_x96=price,
        lower_tick=-100,
        upper_tick=100,
    )

    assert estimate is None


def test_below_range_swaps_all_token1_when_only_token0_is_required():
    price = int(sqrt_ratio_at_tick(-200) * Q96)

    estimate = estimate_swap_to_balance(
        balance0=500,
        balance1=1000,
        sqrt_price_x96=price,
        lower_tick=-100,
        upper_tick=100,
    )

    assert estimate is not None
    assert estimate.token_in == 1
    assert estimate.amount_in == Decimal(1000)


def test_below_range_needs_no_swap_when_token1_balance_is_zero():
    price = int(sqrt_ratio_at_tick(-200) * Q96)

    estimate = estimate_swap_to_balance(
        balance0=500,
        balance1=0,
        sqrt_price_x96=price,
        lower_tick=-100,
        upper_tick=100,
    )

    assert estimate is None


def test_amounts_per_liquidity_at_lower_boundary():
    lower_tick = 200
    upper_tick = 400
    sqrt_price = sqrt_ratio_at_tick(lower_tick)

    amounts = amounts_per_liquidity(
        sqrt_price, lower_tick, upper_tick
    )

    sqrt_lower = sqrt_ratio_at_tick(lower_tick)
    sqrt_upper = sqrt_ratio_at_tick(upper_tick)

    expected_amount0 = (
        (sqrt_upper - sqrt_lower) / (sqrt_lower * sqrt_upper)
    )

    assert amounts.amount0 == expected_amount0
    assert amounts.amount1 == 0


def test_amounts_per_liquidity_at_upper_boundary():
    lower_tick = 200
    upper_tick = 400
    sqrt_price = sqrt_ratio_at_tick(upper_tick)

    amounts = amounts_per_liquidity(
        sqrt_price, lower_tick, upper_tick
    )

    sqrt_lower = sqrt_ratio_at_tick(lower_tick)
    sqrt_upper = sqrt_ratio_at_tick(upper_tick)

    assert amounts.amount0 == 0
    assert amounts.amount1 == sqrt_upper - sqrt_lower


def test_amounts_per_liquidity_inside_range_matches_formulas():
    lower_tick = 200
    upper_tick = 400
    sqrt_price = sqrt_ratio_at_tick(300)

    amounts = amounts_per_liquidity(
        sqrt_price, lower_tick, upper_tick
    )

    sqrt_lower = sqrt_ratio_at_tick(lower_tick)
    sqrt_upper = sqrt_ratio_at_tick(upper_tick)

    expected_amount0 = (
        (sqrt_upper - sqrt_price) / (sqrt_price * sqrt_upper)
    )
    expected_amount1 = sqrt_price - sqrt_lower

    assert amounts.amount0 == expected_amount0
    assert amounts.amount1 == expected_amount1
    assert amounts.amount0 > 0
    assert amounts.amount1 > 0


def test_amounts_per_liquidity_exact_boundaries_and_formula():
    lower_tick = 200
    upper_tick = 400

    lower = amounts_per_liquidity(
        sqrt_ratio_at_tick(lower_tick), lower_tick, upper_tick
    )
    upper = amounts_per_liquidity(
        sqrt_ratio_at_tick(upper_tick), lower_tick, upper_tick
    )

    assert lower.amount1 == 0
    assert upper.amount0 == 0
