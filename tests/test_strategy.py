from dataclasses import replace

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
        lower_tick=219000,
        upper_tick=219200,
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
