from decimal import Decimal

from blockchain.pancake_v3 import PoolState
from strategy import Position, Strategy


def make_pool_state(tick: int) -> PoolState:
    return PoolState(
        address="0x0000000000000000000000000000000000000001",
        token0="0x0000000000000000000000000000000000000002",
        token1="0x0000000000000000000000000000000000000003",
        token0_decimals=6,
        token1_decimals=8,
        fee=500,
        tick_spacing=10,
        sqrt_price_x96=0,
        tick=tick,
        liquidity=1,
        price=Decimal("85391.897326818"),
    )


def test_strategy_in_range():
    strategy = Strategy(Decimal("0.01"))

    state = make_pool_state(-67500)

    position = Position(
        lower_tick=-67610,
        upper_tick=-67400,
    )

    decision = strategy.evaluate(state, position)

    assert decision.in_range is True
    assert decision.lower_tick == -67610
    assert decision.upper_tick == -67400
    assert decision.action == "HOLD"


def test_strategy_out_of_range():
    strategy = Strategy(Decimal("0.01"))

    state = make_pool_state(-67611)

    position = Position(
        lower_tick=-67610,
        upper_tick=-67400,
    )

    decision = strategy.evaluate(state, position)

    assert decision.in_range is False
    assert decision.lower_tick == -67610
    assert decision.upper_tick == -67400
    assert decision.action == "REBALANCE"
