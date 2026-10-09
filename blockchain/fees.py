from decimal import Decimal


def calculate_fees_value_usd(
    amount0_raw: int,
    amount1_raw: int,
    token0_decimals: int,
    token1_decimals: int,
    token0_price_usd: Decimal,
    token1_price_usd: Decimal,
) -> Decimal:
    amount0 = Decimal(amount0_raw) / Decimal(10**token0_decimals)
    amount1 = Decimal(amount1_raw) / Decimal(10**token1_decimals)

    return amount0 * token0_price_usd + amount1 * token1_price_usd
