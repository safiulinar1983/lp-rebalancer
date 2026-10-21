from decimal import Decimal

import pytest

from blockchain.balance_requirements import TokenBalances
from blockchain.liquidity_math import Q96
from blockchain.pancake_v3 import PoolState
from position_opener import (
    OpenPositionPlan,
    build_open_position_plan,
    cap_balances_to_usd,
    plan_open_position,
    range_ticks_for_pool,
)

TOKEN0 = "0x0000000000000000000000000000000000000001"
TOKEN1 = "0x0000000000000000000000000000000000000002"


def make_plan(**overrides):
    values = {
        "network": "base_sepolia",
        "pool_address": "0x1234",
        "current_tick": 0,
        "lower_tick": -600,
        "upper_tick": 600,
        "sqrt_price_x96": int(Q96),
        "token0_balance_raw": 10**18,
        "token1_balance_raw": 10**18,
    }
    values.update(overrides)
    return build_open_position_plan(**values)


def test_plan_sizes_position_within_balances():
    plan = make_plan()

    assert not plan.is_blocked
    assert plan.planned_liquidity > 0
    assert plan.required_token0_raw <= plan.token0_balance_raw
    assert plan.required_token1_raw <= plan.token1_balance_raw
    assert plan.swap is None


def test_plan_blocks_when_range_needs_the_missing_side():
    plan = make_plan(token1_balance_raw=0)

    assert plan.is_blocked
    assert plan.planned_liquidity == 0
    assert "cannot fund positive liquidity" in plan.blocked_reason


def test_plan_swaps_single_sided_balance_to_match_the_range():
    plan = plan_open_position(
        network="base_sepolia",
        pool_address="0x1234",
        current_tick=0,
        lower_tick=-600,
        upper_tick=600,
        sqrt_price_x96=int(Q96),
        token0=TOKEN0,
        token1=TOKEN1,
        token0_balance_raw=10**18,
        token1_balance_raw=0,
        slippage_bps=50,
    )

    assert plan.swap is not None
    assert plan.swap.token_in == TOKEN0
    assert plan.swap.token_out == TOKEN1
    assert plan.swap.min_amount_out_raw <= plan.swap.quoted_amount_out_raw
    assert plan.available_token1_after_swap_raw > 0
    assert not plan.is_blocked


def test_plan_uses_precomputed_swap_projection():
    plan = plan_open_position(
        network="base_sepolia",
        pool_address="0x1234",
        current_tick=0,
        lower_tick=-600,
        upper_tick=600,
        sqrt_price_x96=int(Q96),
        token0=TOKEN0,
        token1=TOKEN1,
        token0_balance_raw=10**18,
        token1_balance_raw=0,
        slippage_bps=50,
        quote=lambda token_in, token_out, amount_in: amount_in // 2,
    )

    assert plan.swap is not None
    assert plan.swap.quoted_amount_out_raw == plan.swap.amount_in_raw // 2
    assert (
        plan.available_token1_after_swap_raw
        == plan.swap.projected_balances.token1_raw
    )


def test_mint_limits_apply_slippage_to_required_amounts():
    plan = make_plan()

    assert plan.mint_amount_limits(50) == (
        plan.required_token0_raw * 9950 // 10_000,
        plan.required_token1_raw * 9950 // 10_000,
    )


def test_plan_rejects_inverted_ticks():
    with pytest.raises(ValueError, match="tick range"):
        make_plan(lower_tick=600, upper_tick=-600)


def test_plan_dataclass_rejects_negative_amounts():
    plan = OpenPositionPlan(
        network="base_sepolia",
        pool_address="0x1234",
        current_tick=0,
        lower_tick=-600,
        upper_tick=600,
        token0_balance_raw=-1,
        token1_balance_raw=10**18,
        required_token0_raw=0,
        required_token1_raw=0,
        available_token0_after_swap_raw=0,
        available_token1_after_swap_raw=10**18,
        planned_liquidity=1,
    )

    with pytest.raises(ValueError, match="cannot be negative"):
        plan.validate()


def test_cap_balances_scales_both_tokens_proportionally():
    balances = TokenBalances(token0_raw=100_000_000, token1_raw=10**18)

    capped = cap_balances_to_usd(
        balances,
        token0_decimals=6,
        token1_decimals=18,
        token0_price_usd=1,
        token1_price_usd=2_000,
        amount_usd=1_050,
    )

    assert capped.token0_raw == 50_000_000
    assert capped.token1_raw == 5 * 10**17


def test_cap_balances_keeps_small_portfolios_untouched():
    balances = TokenBalances(token0_raw=1_000_000, token1_raw=0)

    capped = cap_balances_to_usd(
        balances,
        token0_decimals=6,
        token1_decimals=18,
        token0_price_usd=1,
        token1_price_usd=2_000,
        amount_usd=100,
    )

    assert capped == balances


def test_range_ticks_are_aligned_to_tick_spacing():
    state = PoolState(
        address="0x1234",
        token0=TOKEN0,
        token1=TOKEN1,
        token0_decimals=18,
        token1_decimals=18,
        fee=500,
        tick_spacing=10,
        sqrt_price_x96=int(Q96),
        tick=0,
        liquidity=0,
        price=1,
    )

    lower_tick, upper_tick = range_ticks_for_pool(state, Decimal("0.01"))

    assert lower_tick < upper_tick
    assert lower_tick % 10 == 0
    assert upper_tick % 10 == 0
