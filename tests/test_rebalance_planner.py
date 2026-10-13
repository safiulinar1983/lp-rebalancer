import pytest

from blockchain.liquidity_math import Q96
from rebalance_planner import build_rebalance_plan


def make_plan(**overrides):
    values = {
        "network": "base_sepolia",
        "pool_address": "0x1234",
        "token_id": 82740,
        "current_tick": 219103,
        "old_lower_tick": 219000,
        "old_upper_tick": 219100,
        "new_lower_tick": -100,
        "new_upper_tick": 100,
        "sqrt_price_x96": int(Q96),
        "token0_balance_raw": 100_000_000,
        "token1_balance_raw": 100_000_000,
    }
    values.update(overrides)
    return build_rebalance_plan(**values)


def test_planner_calculates_feasible_liquidity():
    plan = make_plan()

    assert plan.planned_liquidity > 0
    assert plan.required_token0_raw <= plan.token0_balance_raw
    assert plan.required_token1_raw <= plan.token1_balance_raw
    assert plan.balance_check_reason is None


def test_planner_handles_range_requiring_only_token0():
    plan = make_plan(
        new_lower_tick=100,
        new_upper_tick=200,
        token0_balance_raw=1_000_000,
        token1_balance_raw=0,
    )

    assert plan.planned_liquidity > 0
    assert plan.required_token1_raw == 0
    assert plan.balance_check_reason is None


def test_planner_blocks_when_required_token_is_unavailable():
    plan = make_plan(
        new_lower_tick=100,
        new_upper_tick=200,
        token0_balance_raw=0,
        token1_balance_raw=1_000_000,
    )

    assert plan.planned_liquidity == 0
    assert plan.blocked_reason is not None
    assert "cannot fund positive liquidity" in plan.blocked_reason


def test_planner_rejects_invalid_price():
    with pytest.raises(ValueError):
        make_plan(sqrt_price_x96=0)


def test_plan_rejects_negative_planned_liquidity():
    from rebalance_plan import RebalancePlan

    plan = RebalancePlan(
        network="base_sepolia",
        pool_address="0x1234",
        token_id=82740,
        current_tick=10,
        old_lower_tick=0,
        old_upper_tick=10,
        new_lower_tick=20,
        new_upper_tick=30,
        token0_balance_raw=100,
        token1_balance_raw=100,
        planned_liquidity=-1,
    )

    with pytest.raises(ValueError, match="cannot be negative"):
        plan.validate()


def test_plan_after_close_uses_post_close_balances():
    from eth_abi import encode

    from blockchain.close_position_result import (
        decode_decrease_and_collect_results,
    )
    from rebalance_planner import build_rebalance_plan_after_close

    close_result = decode_decrease_and_collect_results(
        [
            encode(["uint256", "uint256"], [100, 200]),
            encode(["uint256", "uint256"], [50_000_000, 60_000_000]),
        ],
        token0_balance_raw=10_000_000,
        token1_balance_raw=20_000_000,
    )

    plan = build_rebalance_plan_after_close(
        close_result=close_result,
        network="base_sepolia",
        pool_address="0x1234",
        token_id=82740,
        current_tick=219103,
        old_lower_tick=219000,
        old_upper_tick=219100,
        new_lower_tick=-100,
        new_upper_tick=100,
        sqrt_price_x96=int(Q96),
    )

    assert plan.token0_balance_raw == 60_000_000
    assert plan.token1_balance_raw == 80_000_000
    assert plan.planned_liquidity > 0
    assert plan.required_token0_raw <= plan.token0_balance_raw
    assert plan.required_token1_raw <= plan.token1_balance_raw
