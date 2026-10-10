from decimal import Decimal

import pytest

from blockchain.price import (
    align_tick,
    is_tick_in_range,
    price_from_tick,
    price_range,
    price_range_ticks,
    price_token1_in_token0,
    tick_from_price,
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
    lower_tick, upper_tick = price_range_ticks(
        Decimal("85391.897326818"),
        Decimal("0.01"),
        10,
        6,
        8,
    )
    assert lower_tick == -67610
    assert upper_tick == -67400
    assert lower_tick % 10 == 0
    assert upper_tick % 10 == 0
    assert lower_tick < upper_tick


@pytest.mark.parametrize(
    ("tick", "expected"),
    [
        (-21, -30),
        (-20, -20),
        (-1, -10),
        (0, 0),
        (1, 0),
        (19, 10),
        (20, 20),
    ],
)
def test_align_tick_rounds_down(tick, expected):
    assert align_tick(tick, 10) == expected


@pytest.mark.parametrize(
    ("tick", "expected"),
    [
        (-21, -20),
        (-20, -20),
        (-1, 0),
        (0, 0),
        (1, 10),
        (19, 20),
        (20, 20),
    ],
)
def test_align_tick_rounds_up(tick, expected):
    assert align_tick(tick, 10, round_up=True) == expected


def test_align_tick_rejects_non_positive_spacing():
    with pytest.raises(ValueError, match="tick_spacing"):
        align_tick(10, 0)


def test_price_range_is_symmetric():
    lower, upper = price_range(Decimal("100"), Decimal("0.01"))
    assert lower == Decimal("99.00")
    assert upper == Decimal("101.00")


@pytest.mark.parametrize(
    ("price", "width"),
    [
        (Decimal("0"), Decimal("0.01")),
        (Decimal("-1"), Decimal("0.01")),
        (Decimal("100"), Decimal("0")),
        (Decimal("100"), Decimal("-0.01")),
    ],
)
def test_price_range_rejects_invalid_arguments(price, width):
    with pytest.raises(ValueError):
        price_range(price, width)


def test_tick_from_price_rejects_non_positive_price():
    with pytest.raises(ValueError, match="price"):
        tick_from_price(Decimal("0"), 6, 8)


def test_is_tick_in_range_lower_inclusive_upper_exclusive():
    assert is_tick_in_range(-67610, -67610, -67400)
    assert is_tick_in_range(-67500, -67610, -67400)
    assert not is_tick_in_range(-67611, -67610, -67400)
    assert not is_tick_in_range(-67400, -67610, -67400)
    assert not is_tick_in_range(-67399, -67610, -67400)


def test_is_tick_in_range_rejects_invalid_range():
    with pytest.raises(ValueError, match="lower_tick"):
        is_tick_in_range(10, 20, 20)
