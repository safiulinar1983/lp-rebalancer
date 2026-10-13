from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING

from blockchain.liquidity_math import Q96, amounts_per_liquidity


@dataclass(frozen=True)
class TokenBalances:
    """Token balances in raw units, such as USDC micro-units and WETH wei."""
    token0_raw: int
    token1_raw: int

    def __post_init__(self):
        for name, value in (
            ("token0_raw", self.token0_raw),
            ("token1_raw", self.token1_raw),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} cannot be negative")


@dataclass(frozen=True)
class BalanceCheck:
    required: TokenBalances
    available: TokenBalances
    deficit: TokenBalances

    @property
    def sufficient(self) -> bool:
        return self.deficit.token0_raw == 0 and self.deficit.token1_raw == 0


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
