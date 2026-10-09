from decimal import Decimal

from blockchain.fees import calculate_fees_value_usd


def test_calculate_fees_value_usd():
    result = calculate_fees_value_usd(
        1_000_000, 1_000_000_000_000_000,
        6, 18, Decimal("1"), Decimal("2300"),
    )
    assert result == Decimal("3.3000")


def test_zero_fees():
    result = calculate_fees_value_usd(
        0, 0, 6, 18, Decimal("1"), Decimal("2300"),
    )
    assert result == Decimal("0")
