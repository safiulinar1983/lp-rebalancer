from decimal import Decimal

from blockchain.price import (
    price_from_tick,
    price_token1_in_token0,
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
