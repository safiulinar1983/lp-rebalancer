from dataclasses import replace
from decimal import Decimal

from web3 import Web3

from config import load_config
from blockchain.pancake_v3 import PancakeV3Pool
from strategy import Strategy, Position


def test_strategy_inside_and_outside_range():
    config = load_config()

    w3 = Web3(Web3.HTTPProvider(config.rpc_url))

    assert w3.is_connected()

    pool = PancakeV3Pool(
        w3=w3,
        address=config.pool_address,
    )

    strategy = Strategy(
        range_half_width=config.range_half_width,
    )

    position = Position(
        token_id=82740,
        token0="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        token1="0x4200000000000000000000000000000000000006",
        fee=500,
        lower_tick=219000,
        upper_tick=219200,
        liquidity=339297883302,
        tokens_owed0=0,
        tokens_owed1=0,
    )

    pool_state = pool.read_state()

    pool_inside = replace(
        pool_state,
        tick=219103,
    )

    pool_outside = replace(
        pool_state,
        tick=219250,
    )

    inside_decision = strategy.evaluate(
        pool_inside,
        position,
    )

    outside_decision = strategy.evaluate(
        pool_outside,
        position,
    )

    assert inside_decision.action == "HOLD"
    assert inside_decision.in_range is True

    assert outside_decision.action == "REBALANCE"
    assert outside_decision.in_range is False

    # Fees above threshold: collect fees
    collect_decision = strategy.evaluate(
        pool_inside,
        position,
        fees_value_usd=Decimal("0.15"),
    )
    assert collect_decision.action == "COLLECT_FEES"

    # Fees below threshold: hold
    hold_decision = strategy.evaluate(
        pool_inside,
        position,
        fees_value_usd=Decimal("0.05"),
    )
    assert hold_decision.action == "HOLD"

    # Out of range: rebalance takes priority
    rebalance_decision = strategy.evaluate(
        pool_outside,
        position,
        fees_value_usd=Decimal("0.15"),
    )
    assert rebalance_decision.action == "REBALANCE"
