"""Planning for a brand-new V3 LP position.

A rebalance closes an existing NFT and re-mints with the same capital. Opening
the first position is different: the wallet may hold only one of the pool
tokens, so the planner first decides how much to swap, then sizes the position
from the projected balances.

This module is pure: it reads no RPC and sends no transactions. The CLI in
``scripts/open_position.py`` supplies the current pool state, quotes swaps and
executes the planned calls.
"""

from dataclasses import dataclass
from decimal import Decimal

from blockchain.balance_requirements import (
    LiquidityAllocation,
    TokenBalances,
    allocate_liquidity,
)
from blockchain.pancake_v3 import PoolState
from blockchain.price import price_range_ticks
from blockchain.slippage import slippage_floor
from blockchain.swap_plan import SwapPlan
from rebalance_planner import plan_swap_to_match_ratio


@dataclass(frozen=True)
class OpenPositionPlan:
    """Affordable new position, including the optional ratio-fixing swap."""

    network: str
    pool_address: str

    current_tick: int
    lower_tick: int
    upper_tick: int

    token0_balance_raw: int
    token1_balance_raw: int

    required_token0_raw: int
    required_token1_raw: int
    available_token0_after_swap_raw: int
    available_token1_after_swap_raw: int

    planned_liquidity: int
    swap: SwapPlan | None = None
    blocked_reason: str | None = None

    @property
    def swap_required(self) -> bool:
        """Whether the plan specifies a positive token swap."""
        return self.swap is not None and self.swap.amount_in_raw > 0

    @property
    def is_blocked(self) -> bool:
        """Whether execution must be prevented."""
        return self.blocked_reason is not None or self.planned_liquidity <= 0

    def mint_amount_limits(self, slippage_bps: int) -> tuple[int, int]:
        """Return ``(amount0Min, amount1Min)`` for the mint call."""
        return (
            slippage_floor(self.required_token0_raw, slippage_bps),
            slippage_floor(self.required_token1_raw, slippage_bps),
        )

    def validate(self) -> None:
        """Reject structurally invalid plans before any execution."""
        if not self.network:
            raise ValueError("Network must not be empty")

        if not self.pool_address:
            raise ValueError("Pool address must not be empty")

        if self.lower_tick >= self.upper_tick:
            raise ValueError("Position tick range is invalid")

        for name, value in (
            ("token0_balance_raw", self.token0_balance_raw),
            ("token1_balance_raw", self.token1_balance_raw),
            ("required_token0_raw", self.required_token0_raw),
            ("required_token1_raw", self.required_token1_raw),
            (
                "available_token0_after_swap_raw",
                self.available_token0_after_swap_raw,
            ),
            (
                "available_token1_after_swap_raw",
                self.available_token1_after_swap_raw,
            ),
            ("planned_liquidity", self.planned_liquidity),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} cannot be negative")

        if self.swap is not None and not isinstance(self.swap, SwapPlan):
            raise ValueError("swap must be a SwapPlan or None")

        if self.swap is not None:
            if self.swap.amount_in_raw <= 0:
                raise ValueError("Swap input amount must be positive")
            if self.swap.token_in.lower() == self.swap.token_out.lower():
                raise ValueError("Swap input and output tokens must differ")
            if self.swap.min_amount_out_raw > self.swap.quoted_amount_out_raw:
                raise ValueError(
                    "Minimum swap output cannot exceed the quoted output"
                )


def _token_balances(
    token0_balance_raw: int,
    token1_balance_raw: int,
) -> TokenBalances:
    """Build balances and let ``TokenBalances`` validate the raw integers."""
    return TokenBalances(
        token0_raw=token0_balance_raw,
        token1_raw=token1_balance_raw,
    )


def build_open_position_plan(
    *,
    network: str,
    pool_address: str,
    current_tick: int,
    lower_tick: int,
    upper_tick: int,
    sqrt_price_x96: int,
    token0_balance_raw: int,
    token1_balance_raw: int,
    swap: SwapPlan | None = None,
) -> OpenPositionPlan:
    """Size a new position from the balances left after the optional swap."""
    if lower_tick >= upper_tick:
        raise ValueError("Position tick range is invalid")

    balances = _token_balances(
        token0_balance_raw,
        token1_balance_raw,
    )
    available = balances if swap is None else swap.projected_balances

    allocation: LiquidityAllocation = allocate_liquidity(
        sqrt_price_x96,
        lower_tick,
        upper_tick,
        available,
    )

    plan = OpenPositionPlan(
        network=network,
        pool_address=pool_address,
        current_tick=current_tick,
        lower_tick=lower_tick,
        upper_tick=upper_tick,
        token0_balance_raw=balances.token0_raw,
        token1_balance_raw=balances.token1_raw,
        required_token0_raw=allocation.required.token0_raw,
        required_token1_raw=allocation.required.token1_raw,
        available_token0_after_swap_raw=available.token0_raw,
        available_token1_after_swap_raw=available.token1_raw,
        planned_liquidity=allocation.liquidity,
        swap=swap,
        blocked_reason=allocation.blocked_reason,
    )
    plan.validate()
    return plan


def plan_open_position(
    *,
    network: str,
    pool_address: str,
    current_tick: int,
    lower_tick: int,
    upper_tick: int,
    sqrt_price_x96: int,
    token0: str,
    token1: str,
    token0_balance_raw: int,
    token1_balance_raw: int,
    slippage_bps: int,
    quote=None,
) -> OpenPositionPlan:
    """Plan a swap that matches the range ratio, then size the position.

    ``quote`` is an optional callable ``(token_in, token_out, amount_in)`` that
    returns a raw output amount. Without it, the local constant-product estimate
    is used and execution must stay in ``DRY_RUN``.
    """
    balances = _token_balances(
        token0_balance_raw,
        token1_balance_raw,
    )

    swap = plan_swap_to_match_ratio(
        token0=token0,
        token1=token1,
        sqrt_price_x96=sqrt_price_x96,
        lower_tick=lower_tick,
        upper_tick=upper_tick,
        token0_balance_raw=balances.token0_raw,
        token1_balance_raw=balances.token1_raw,
        slippage_bps=slippage_bps,
        quote=quote,
    )

    return build_open_position_plan(
        network=network,
        pool_address=pool_address,
        current_tick=current_tick,
        lower_tick=lower_tick,
        upper_tick=upper_tick,
        sqrt_price_x96=sqrt_price_x96,
        token0_balance_raw=balances.token0_raw,
        token1_balance_raw=balances.token1_raw,
        swap=swap,
    )


def range_ticks_for_pool(
    state: PoolState,
    half_width: Decimal,
) -> tuple[int, int]:
    """Return the strategy-style range around the current pool price."""
    if not isinstance(half_width, Decimal):
        raise TypeError("half_width must be a Decimal")

    if half_width <= 0:
        raise ValueError("half_width must be positive")

    lower_tick, upper_tick = price_range_ticks(
        state.price,
        half_width,
        state.tick_spacing,
        state.token0_decimals,
        state.token1_decimals,
    )

    if lower_tick >= upper_tick:
        raise ValueError("calculated tick range is invalid")

    return lower_tick, upper_tick


def cap_balances_to_usd(
    balances: TokenBalances,
    *,
    token0_decimals: int,
    token1_decimals: int,
    token0_price_usd: Decimal,
    token1_price_usd: Decimal,
    amount_usd: Decimal,
) -> TokenBalances:
    """Scale balances down proportionally so their total value fits a budget.

    Native ETH used for gas is not part of ``balances``: only the two pool
    tokens are capped. The function never increases a balance.
    """
    if not isinstance(balances, TokenBalances):
        raise TypeError("balances must be TokenBalances")

    if amount_usd <= 0:
        raise ValueError("amount_usd must be positive")

    if token0_price_usd <= 0 or token1_price_usd <= 0:
        raise ValueError("token prices must be positive")

    token0_value = (
        Decimal(balances.token0_raw)
        / (Decimal(10) ** token0_decimals)
        * token0_price_usd
    )
    token1_value = (
        Decimal(balances.token1_raw)
        / (Decimal(10) ** token1_decimals)
        * token1_price_usd
    )
    total_value = token0_value + token1_value

    if total_value <= amount_usd:
        return balances

    scale = amount_usd / total_value

    return TokenBalances(
        token0_raw=int(Decimal(balances.token0_raw) * scale),
        token1_raw=int(Decimal(balances.token1_raw) * scale),
    )

