from decimal import Decimal

from blockchain.fees import calculate_fees_value_usd


def test_calculate_fees_value_usd():
    result = calculate_fees_value_usd(
        amount0_raw=1_000_000,
        amount1_raw=1_000_000_000_000_000,
        token0_decimals=6,
        token1_decimals=18,
        token1_price_usd=Decimal("2300"),
    )
    assert result == Decimal("3.3")


def test_zero_fees():
    result = calculate_fees_value_usd(
        amount0_raw=0,
        amount1_raw=0,
        token0_decimals=6,
        token1_decimals=18,
        token1_price_usd=Decimal("2300"),
    )
    assert result == Decimal("0")
