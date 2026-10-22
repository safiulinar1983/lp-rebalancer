"""Gas limits and gas-cost budgeting for the rebalance cycle.

Everything here is a pure calculation: the gas price and the USD price of the
native token are passed in by the caller, nothing is read from the network.
"""

from dataclasses import dataclass
from decimal import Decimal

# Gas limits for the state-changing operations of a rebalance cycle. The values
# follow the manual scripts (``scripts/mint_position.py`` mints with 500_000)
# with headroom for the extra token transfers a cycle operation performs.
GAS_LIMITS = {
    "approve": 80_000,
    "collect": 200_000,
    "increase_liquidity": 500_000,
    "decrease_liquidity": 400_000,
    "close_position": 700_000,
    "mint": 700_000,
    "burn": 200_000,
    "swap": 400_000,
}

DEFAULT_GAS_LIMIT = 500_000

WEI_PER_NATIVE = Decimal(10**18)


def wei_to_native(wei: int) -> Decimal:
    """Convert a non-negative wei amount to native-token units."""
    if isinstance(wei, bool) or not isinstance(wei, int) or wei < 0:
        raise ValueError("wei must be a non-negative integer")

    return Decimal(wei) / WEI_PER_NATIVE


def gas_limit_for(operation: str) -> int:
    """Return the gas limit of a named cycle operation."""
    if not isinstance(operation, str) or not operation.strip():
        raise ValueError("operation must be a non-empty string")

    try:
        return GAS_LIMITS[operation.strip()]
    except KeyError as exc:
        raise ValueError(f"Unknown gas limit operation: {operation}") from exc


@dataclass(frozen=True)
class GasBudget:
    """Cost of one operation compared with the configured ceiling."""

    cost_native: Decimal
    cost_usd: Decimal | None
    max_cost_usd: Decimal | None
    reason: str | None = None

    @property
    def allowed(self) -> bool:
        return self.reason is None


def check_gas_budget(
    gas_limit: int,
    gas_price_wei: int,
    max_gas_cost_usd: Decimal | None,
    native_price_usd: Decimal | None,
) -> GasBudget:
    """Check whether one operation fits into ``max_gas_cost_usd``.

    ``max_gas_cost_usd`` of ``None`` disables the check. When the ceiling is
    set, ``native_price_usd`` must also be available, otherwise the check fails
    with an explicit reason instead of silently allowing the transaction.
    """
    if (
        isinstance(gas_limit, bool)
        or not isinstance(gas_limit, int)
        or gas_limit <= 0
    ):
        raise ValueError("gas_limit must be a positive integer")

    if (
        isinstance(gas_price_wei, bool)
        or not isinstance(gas_price_wei, int)
        or gas_price_wei <= 0
    ):
        raise ValueError("gas_price_wei must be a positive integer")

    if max_gas_cost_usd is not None and max_gas_cost_usd < 0:
        raise ValueError("max_gas_cost_usd cannot be negative")

    if native_price_usd is not None and native_price_usd <= 0:
        raise ValueError("native_price_usd must be positive")

    cost_native = Decimal(gas_limit * gas_price_wei) / WEI_PER_NATIVE

    if max_gas_cost_usd is None:
        return GasBudget(
            cost_native=cost_native,
            cost_usd=None,
            max_cost_usd=None,
        )

    if native_price_usd is None:
        return GasBudget(
            cost_native=cost_native,
            cost_usd=None,
            max_cost_usd=max_gas_cost_usd,
            reason=(
                "Gas budget is configured but the native token price is "
                "unknown, so the gas cost cannot be valued in USD"
            ),
        )

    cost_usd = cost_native * native_price_usd

    if cost_usd > max_gas_cost_usd:
        return GasBudget(
            cost_native=cost_native,
            cost_usd=cost_usd,
            max_cost_usd=max_gas_cost_usd,
            reason=(
                f"Gas cost ${cost_usd:.6f} exceeds the configured limit "
                f"${max_gas_cost_usd}"
            ),
        )

    return GasBudget(
        cost_native=cost_native,
        cost_usd=cost_usd,
        max_cost_usd=max_gas_cost_usd,
    )
