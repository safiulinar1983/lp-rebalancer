"""Balance requirements for opening a new V3 position.

``TokenBalances`` is re-exported from ``blockchain.token_balances`` so that a
single definition is shared by every module that deals with wallet assets.
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from blockchain.liquidity_math import Q96, amounts_per_liquidity
from blockchain.token_balances import TokenBalances

__all__ = [
    "BalanceCheck",
    "LiquidityAllocation",
    "TokenBalances",
    "allocate_liquidity",
    "check_sufficient_balances",
    "max_liquidity_for_balances",
    "required_token_amounts",
]


@dataclass(frozen=True)
class BalanceCheck:
    required: TokenBalances
    available: TokenBalances
    deficit: TokenBalances

    @property
    def sufficient(self) -> bool:
        return self.deficit.token0_raw == 0 and self.deficit.token1_raw == 0


@dataclass(frozen=True)
class LiquidityAllocation:
    """Liquidity affordable with the balances and the tokens it consumes."""

    liquidity: int
    required: TokenBalances
    blocked_reason: str | None = None

    @property
    def feasible(self) -> bool:
        return self.blocked_reason is None and self.liquidity > 0


def required_token_amounts(
    sqrt_price_x96: int,
    lower_tick: int,
    upper_tick: int,
    liquidity: int,
) -> TokenBalances:
    """Estimate the raw token amounts required for a V3 liquidity amount.

    Amounts are rounded up to avoid understating the required balances.
    This is a local calculation, not an on-chain quote or transaction.
    """
    if isinstance(sqrt_price_x96, bool) or not isinstance(sqrt_price_x96, int):
        raise ValueError("sqrt_price_x96 must be an integer")
    if sqrt_price_x96 <= 0:
        raise ValueError("sqrt_price_x96 must be positive")
    if isinstance(liquidity, bool) or not isinstance(liquidity, int):
        raise ValueError("liquidity must be an integer")
    if liquidity <= 0:
        raise ValueError("liquidity must be positive")

    sqrt_price = Decimal(sqrt_price_x96) / Q96
    per_liquidity = amounts_per_liquidity(
        sqrt_price, lower_tick, upper_tick
    )

    amount0 = (per_liquidity.amount0 * liquidity).to_integral_value(
        rounding=ROUND_CEILING
    )
    amount1 = (per_liquidity.amount1 * liquidity).to_integral_value(
        rounding=ROUND_CEILING
    )

    return TokenBalances(int(amount0), int(amount1))


def max_liquidity_for_balances(
    sqrt_price_x96: int,
    lower_tick: int,
    upper_tick: int,
    available: TokenBalances,
) -> int:
    """Return the maximum integer liquidity affordable with available balances.

    Amounts are calculated in raw token units. The result is a local
    mathematical estimate, not a guarantee that an on-chain mint will succeed.
    Returns zero when the available balances cannot fund positive liquidity.
    """
    if isinstance(sqrt_price_x96, bool) or not isinstance(sqrt_price_x96, int):
        raise ValueError("sqrt_price_x96 must be an integer")
    if sqrt_price_x96 <= 0:
        raise ValueError("sqrt_price_x96 must be positive")
    if not isinstance(available, TokenBalances):
        raise TypeError("available must be TokenBalances")

    sqrt_price = Decimal(sqrt_price_x96) / Q96
    per_liquidity = amounts_per_liquidity(
        sqrt_price, lower_tick, upper_tick
    )

    limits = []
    if per_liquidity.amount0 > 0:
        limits.append(
            Decimal(available.token0_raw) / per_liquidity.amount0
        )
    if per_liquidity.amount1 > 0:
        limits.append(
            Decimal(available.token1_raw) / per_liquidity.amount1
        )

    if not limits:
        raise ValueError("Invalid target token amounts")

    return max(0, int(min(limits)))


def allocate_liquidity(
    sqrt_price_x96: int,
    lower_tick: int,
    upper_tick: int,
    available: TokenBalances,
) -> LiquidityAllocation:
    """Return the largest liquidity whose required amounts fit the balances.

    ``max_liquidity_for_balances`` floors the ratio of balances to the amounts
    per unit of liquidity. Rounding the required amounts up can still push one
    side above the balance by a raw unit, so the result is verified and, when
    needed, reduced with a binary search. This is a local calculation, not an
    on-chain quote.
    """
    if not isinstance(available, TokenBalances):
        raise TypeError("available must be TokenBalances")

    liquidity = max_liquidity_for_balances(
        sqrt_price_x96,
        lower_tick,
        upper_tick,
        available,
    )

    def calculate_requirements(value: int) -> TokenBalances:
        return required_token_amounts(
            sqrt_price_x96,
            lower_tick,
            upper_tick,
            value,
        )

    required = (
        calculate_requirements(liquidity)
        if liquidity > 0
        else TokenBalances(token0_raw=0, token1_raw=0)
    )

    if liquidity > 0 and (
        required.token0_raw > available.token0_raw
        or required.token1_raw > available.token1_raw
    ):
        low, high = 0, liquidity

        while low < high:
            middle = (low + high + 1) // 2
            candidate = calculate_requirements(middle)

            if (
                candidate.token0_raw <= available.token0_raw
                and candidate.token1_raw <= available.token1_raw
            ):
                low = middle
            else:
                high = middle - 1

        liquidity = low
        required = (
            calculate_requirements(liquidity)
            if liquidity > 0
            else TokenBalances(token0_raw=0, token1_raw=0)
        )

    blocked_reason = (
        None
        if liquidity > 0
        else (
            "Available balances cannot fund positive liquidity "
            "in the target range"
        )
    )

    return LiquidityAllocation(
        liquidity=liquidity,
        required=required,
        blocked_reason=blocked_reason,
    )


def check_sufficient_balances(
    available: TokenBalances,
    required: TokenBalances,
) -> BalanceCheck:
    """Compare available wallet balances with the required raw token amounts."""
    if not isinstance(available, TokenBalances):
        raise TypeError("available must be TokenBalances")
    if not isinstance(required, TokenBalances):
        raise TypeError("required must be TokenBalances")

    return BalanceCheck(
        required=required,
        available=available,
        deficit=TokenBalances(
            max(required.token0_raw - available.token0_raw, 0),
            max(required.token1_raw - available.token1_raw, 0),
        ),
    )
