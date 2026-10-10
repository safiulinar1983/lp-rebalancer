from dataclasses import replace
from decimal import Decimal

import pytest

from blockchain.pancake_v3 import PoolState
from blockchain.price import price_from_tick
from strategy import Position, Strategy


@pytest.fixture
def pool_state():
    return PoolState(
        address="0x0000000000000000000000000000000000000001",
        token0="0x0000000000000000000000000000000000000002",
        token1="0x0000000000000000000000000000000000000003",
        token0_decimals=6,
        token1_decimals=18,
        fee=500,
        tick_spacing=10,
        sqrt_price_x96=1,
        tick=219103,
        liquidity=1000000,
        price=Decimal("1"),
    )


@pytest.fixture
def position():
    return Position(
        token_id=82740,
        token0="0x0000000000000000000000000000000000000002",
        token1="0x0000000000000000000000000000000000000003",
        fee=500,
        lower_tick=219000,
        upper_tick=219200,
        liquidity=339297883302,
        tokens_owed0=0,
        tokens_owed1=0,
    )


@pytest.fixture
def strategy():
    return Strategy(
        range_half_width=Decimal("0.01"),
    )


def test_strategy_holds_when_inside_range(
    strategy, pool_state, position
):
    decision = strategy.evaluate(pool_state, position)

    assert decision.action == "HOLD"
    assert decision.in_range is True


def test_strategy_rebalances_when_below_range(
    strategy, pool_state, position
):
    state = replace(
        pool_state,
        tick=218999,
        price=price_from_tick(218999, 6, 18),
    )

    decision = strategy.evaluate(state, position)

    assert decision.action == "REBALANCE"
    assert decision.in_range is False


def test_strategy_rebalances_when_above_range(
    strategy, pool_state, position
):
    state = replace(
        pool_state,
        tick=219201,
        price=price_from_tick(219201, 6, 18),
    )

    decision = strategy.evaluate(state, position)

    assert decision.action == "REBALANCE"
    assert decision.in_range is False


def test_strategy_collects_fees_above_threshold(
    strategy, pool_state, position
):
    decision = strategy.evaluate(
        pool_state,
        position,
        fees_value_usd=Decimal("0.15"),
    )

    assert decision.action == "COLLECT_FEES"
    assert decision.in_range is True


def test_strategy_holds_when_fees_below_threshold(
    strategy, pool_state, position
):
    decision = strategy.evaluate(
        pool_state,
        position,
        fees_value_usd=Decimal("0.05"),
    )

    assert decision.action == "HOLD"


def test_rebalance_has_priority_over_fee_collection(
    strategy, pool_state, position
):
    state = replace(
        pool_state,
        tick=219250,
        price=price_from_tick(219250, 6, 18),
    )

    decision = strategy.evaluate(
        state,
        position,
        fees_value_usd=Decimal("0.15"),
    )

    assert decision.action == "REBALANCE"
    assert decision.in_range is False


def test_strategy_rejects_non_positive_range_width():
    with pytest.raises(ValueError, match="range_half_width"):
        Strategy(range_half_width=Decimal("0"))


def test_strategy_rejects_negative_fee_threshold():
    with pytest.raises(ValueError, match="fee_threshold_usd"):
        Strategy(
            range_half_width=Decimal("0.01"),
            fee_threshold_usd=Decimal("-0.01"),
        )


def test_strategy_proposes_new_range_when_out_of_range(
    strategy, pool_state, position
):
    state = replace(
        pool_state,
        tick=219250,
        price=price_from_tick(219250, 6, 18),
    )

    decision = strategy.evaluate(state, position)

    assert decision.action == "REBALANCE"
    assert decision.proposed_lower_tick is not None
    assert decision.proposed_upper_tick is not None
    assert decision.proposed_lower_tick < state.tick
    assert decision.proposed_upper_tick > state.tick
    assert decision.proposed_lower_tick % state.tick_spacing == 0
    assert decision.proposed_upper_tick % state.tick_spacing == 0


def test_strategy_does_not_propose_new_range_when_in_range(
    strategy, pool_state, position
):
    decision = strategy.evaluate(pool_state, position)

    assert decision.action == "HOLD"
    assert decision.proposed_lower_tick is None
    assert decision.proposed_upper_tick is None
