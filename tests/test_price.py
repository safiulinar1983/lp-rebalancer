from decimal import Decimal

from blockchain.price import (
    price_from_tick,
    price_token1_in_token0,
    price_range_ticks,
)


def test_price_from_sqrt_price():
    price = price_token1_in_token0(
        2711260532281758252337625293,
        6,
        8,
    )

    assert Decimal("85391") < price < Decimal("85392")


def test_price_from_tick():
    price = price_from_tick(-67502, 6, 8)

    assert Decimal("85394") < price < Decimal("85395")


def test_price_tick_direction():
    lower = price_from_tick(-67510, 6, 8)
    upper = price_from_tick(-67500, 6, 8)

    assert lower > upper


def test_price_range_ticks():
    current_price = Decimal("85391.897326818")

    lower_tick, upper_tick = price_range_ticks(
        current_price,
        Decimal("0.01"),
        10,
        6,
        8,
    )

    assert lower_tick == -67610
    assert upper_tick == -67400
