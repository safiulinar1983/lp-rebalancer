from dataclasses import dataclass
from decimal import Decimal, getcontext

getcontext().prec = 60

Q96 = Decimal(2**96)
TICK_BASE = Decimal("1.0001")


@dataclass(frozen=True)
class TokenAmounts:
    amount0: Decimal
    amount1: Decimal


@dataclass(frozen=True)
class SwapEstimate:
    token_in: int  # 0 or 1
    amount_in: Decimal
    expected_amount_out: Decimal


def sqrt_ratio_at_tick(tick: int) -> Decimal:
    """Return sqrt(token1_raw / token0_raw) at a V3 tick."""
    if not -887272 <= tick <= 887272:
        raise ValueError("Tick outside supported V3 bounds")
    return TICK_BASE ** (Decimal(tick) / Decimal(2))


def amounts_per_liquidity(
    sqrt_price: Decimal,
    lower_tick: int,
    upper_tick: int,
) -> TokenAmounts:
    """Raw token amounts required per unit of liquidity."""
    if sqrt_price <= 0:
        raise ValueError("sqrt_price must be positive")
    if lower_tick >= upper_tick:
        raise ValueError("lower_tick must be less than upper_tick")

    sqrt_lower = sqrt_ratio_at_tick(lower_tick)
    sqrt_upper = sqrt_ratio_at_tick(upper_tick)

    if sqrt_price <= sqrt_lower:
        return TokenAmounts(
            amount0=(sqrt_upper - sqrt_lower)
            / (sqrt_lower * sqrt_upper),
            amount1=Decimal(0),
        )

    if sqrt_price >= sqrt_upper:
        return TokenAmounts(
            amount0=Decimal(0),
            amount1=sqrt_upper - sqrt_lower,
        )

    return TokenAmounts(
        amount0=(sqrt_upper - sqrt_price)
        / (sqrt_price * sqrt_upper),
        amount1=sqrt_price - sqrt_lower,
    )


def estimate_swap_to_balance(
    balance0: int,
    balance1: int,
    sqrt_price_x96: int,
    lower_tick: int,
    upper_tick: int,
) -> SwapEstimate | None:
    """
    Estimate the swap needed to match the token ratio for a new position.

    Assumes a spot-price swap with no fees or slippage.
    Returns None if the current balances already have the required ratio.
    """
    if balance0 < 0 or balance1 < 0:
        raise ValueError("Token balances cannot be negative")
    if sqrt_price_x96 <= 0:
        raise ValueError("sqrt_price_x96 must be positive")

    sqrt_price = Decimal(sqrt_price_x96) / Q96
    amounts = amounts_per_liquidity(
        sqrt_price, lower_tick, upper_tick
    )

    if amounts.amount0 == 0 and amounts.amount1 == 0:
        raise ValueError("Invalid target token amounts")

    if amounts.amount0 == 0:
        if balance0 == 0:
            return None
        return SwapEstimate(
            token_in=0,
            amount_in=Decimal(balance0),
            expected_amount_out=Decimal(balance0) * sqrt_price**2,
        )

    if amounts.amount1 == 0:
        if balance1 == 0:
            return None
        return SwapEstimate(
            token_in=1,
            amount_in=Decimal(balance1),
            expected_amount_out=Decimal(balance1) / (sqrt_price**2),
        )

    # Required raw-unit ratio: token0 / token1.
    ratio = amounts.amount0 / amounts.amount1
    price1_per_0 = sqrt_price**2

    # Solve (balance0 - swap0) / (balance1 + swap0 * price) = ratio.
    swap0 = (
        Decimal(balance0) - ratio * Decimal(balance1)
    ) / (Decimal(1) + ratio * price1_per_0)

    if swap0 > 0:
        if swap0 > Decimal(balance0):
            raise ValueError("Calculated token0 swap exceeds available balance")
        return SwapEstimate(
            token_in=0,
            amount_in=swap0,
            expected_amount_out=swap0 * price1_per_0,
        )

    # Solve (balance0 + swap1 / price) / (balance1 - swap1) = ratio.
    swap1 = (
        ratio * Decimal(balance1) - Decimal(balance0)
    ) / (ratio + Decimal(1) / price1_per_0)

    if swap1 <= 0:
        return None

    if swap1 > Decimal(balance1):
        raise ValueError("Calculated token1 swap exceeds available balance")

    return SwapEstimate(
        token_in=1,
        amount_in=swap1,
        expected_amount_out=swap1 / price1_per_0,
    )
