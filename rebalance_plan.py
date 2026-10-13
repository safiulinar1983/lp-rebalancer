from dataclasses import dataclass


@dataclass(frozen=True)
class RebalancePlan:
    """Description of a rebalance cycle. Does not execute transactions."""

    network: str
    pool_address: str
    token_id: int

    current_tick: int
    old_lower_tick: int
    old_upper_tick: int
    new_lower_tick: int
    new_upper_tick: int

    token0_balance_raw: int
    token1_balance_raw: int

    swap_token_in: str | None = None
    swap_token_out: str | None = None
    swap_amount_in_raw: int | None = None
    quoted_amount_out_raw: int | None = None
    min_amount_out_raw: int | None = None

    estimated_gas_cost_usd: float | None = None
    max_gas_cost_usd: float | None = None

    blocked_reason: str | None = None

    @property
    def requires_rebalance(self) -> bool:
        """Whether the current tick is outside the existing position."""
        return not (
            self.old_lower_tick <= self.current_tick < self.old_upper_tick
        )

    @property
    def swap_required(self) -> bool:
        """Whether the plan specifies a positive token swap."""
        return (
            self.swap_amount_in_raw is not None
            and self.swap_amount_in_raw > 0
        )

    @property
    def is_blocked(self) -> bool:
        """Whether execution must be prevented."""
        if self.blocked_reason:
            return True

        if self.max_gas_cost_usd is not None:
            if self.estimated_gas_cost_usd is None:
                return True
            if self.estimated_gas_cost_usd > self.max_gas_cost_usd:
                return True

        return False

    def validate(self) -> None:
        """Reject structurally invalid plans before any execution."""

        if not self.network:
            raise ValueError("Network must not be empty")

        if not self.pool_address:
            raise ValueError("Pool address must not be empty")

        if self.token_id <= 0:
            raise ValueError("token_id must be positive")

        if self.old_lower_tick >= self.old_upper_tick:
            raise ValueError("Old position tick range is invalid")

        if self.new_lower_tick >= self.new_upper_tick:
            raise ValueError("New position tick range is invalid")

        if self.token0_balance_raw < 0 or self.token1_balance_raw < 0:
            raise ValueError("Token balances cannot be negative")

        swap_fields = (
            self.swap_token_in,
            self.swap_token_out,
            self.swap_amount_in_raw,
        )

        if any(value is not None for value in swap_fields):
            if any(value is None for value in swap_fields):
                raise ValueError("Swap input fields must be provided together")

            if self.swap_amount_in_raw <= 0:
                raise ValueError("Swap input amount must be positive")

            if self.swap_token_in.lower() == self.swap_token_out.lower():
                raise ValueError("Swap input and output tokens must differ")

        # Validate numeric values before comparing them.
        if self.quoted_amount_out_raw is not None:
            if self.quoted_amount_out_raw <= 0:
                raise ValueError("Quoted output must be positive")

        if self.min_amount_out_raw is not None:
            if self.min_amount_out_raw <= 0:
                raise ValueError("Minimum output must be positive")

        # A swap requires both a quote and a slippage limit.
        if self.swap_required:
            if self.quoted_amount_out_raw is None:
                raise ValueError("Swap requires a quoted output")
            if self.min_amount_out_raw is None:
                raise ValueError("Swap requires a minimum output")

        # A minimum output without a quote is invalid even without a swap.
        if (
            self.min_amount_out_raw is not None
            and self.quoted_amount_out_raw is None
        ):
            raise ValueError("Minimum output requires a quote")

        if (
            self.min_amount_out_raw is not None
            and self.quoted_amount_out_raw is not None
            and self.min_amount_out_raw > self.quoted_amount_out_raw
        ):
            raise ValueError(
                "Minimum output cannot exceed quoted output"
            )

        if self.estimated_gas_cost_usd is not None:
            if self.estimated_gas_cost_usd < 0:
                raise ValueError("Estimated gas cost cannot be negative")

        if self.max_gas_cost_usd is not None:
            if self.max_gas_cost_usd < 0:
                raise ValueError("Maximum gas cost cannot be negative")
