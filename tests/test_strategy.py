from decimal import Decimal

from blockchain.pancake_v3 import PoolState
from strategy import Strategy


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

    decision = strategy.evaluate(state)

    assert decision.in_range is True
    assert decision.lower_tick == -67610
    assert decision.upper_tick == -67400


def test_strategy_out_of_range():
    strategy = Strategy(Decimal("0.01"))

    state = make_pool_state(-67611)

    decision = strategy.evaluate(state)

    assert decision.in_range is False
    assert decision.lower_tick == -67610
    assert decision.upper_tick == -67400
