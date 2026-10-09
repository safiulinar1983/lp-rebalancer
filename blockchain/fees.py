from decimal import Decimal


def calculate_fees_value_usd(
    amount0_raw: int,
    amount1_raw: int,
    token0_decimals: int,
    token1_decimals: int,
    token1_price_usd: Decimal,
) -> Decimal:
    token0_value = Decimal(amount0_raw) / Decimal(10**token0_decimals)
    token1_amount = Decimal(amount1_raw) / Decimal(10**token1_decimals)
    return token0_value + token1_amount * token1_price_usd
