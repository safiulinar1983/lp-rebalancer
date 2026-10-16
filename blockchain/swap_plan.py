"""Value object for the ratio-fixing swap of a rebalance cycle.

The cycle needs one swap before it can add liquidity: the wallet holds two
tokens in whatever proportion the previous position left behind, while a new
position only accepts them in the ratio of the target range. This module holds
the swap that closes that gap; it performs no RPC calls.
"""

from dataclasses import dataclass

from blockchain.token_balances import TokenBalances


@dataclass(frozen=True)
class SwapPlan:
    """A single exact-input swap and the balances it is expected to leave.

    All amounts are integer raw token units. ``token_in_index`` is 0 when
    token0 is sold and 1 when token1 is sold.
    """

    token_in: str
    token_out: str
    token_in_index: int
    amount_in_raw: int
    quoted_amount_out_raw: int
    min_amount_out_raw: int
    projected_balances: TokenBalances

    def __post_init__(self) -> None:
        if self.token_in_index not in (0, 1):
            raise ValueError("token_in_index must be 0 or 1")

        for name, value in (
            ("token_in", self.token_in),
            ("token_out", self.token_out),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty address")

        if self.token_in.lower() == self.token_out.lower():
            raise ValueError("Swap input and output tokens must differ")

        if isinstance(self.amount_in_raw, bool) or not isinstance(
            self.amount_in_raw, int
        ):
            raise ValueError("amount_in_raw must be an integer")

        if self.amount_in_raw <= 0:
            raise ValueError("amount_in_raw must be positive")

        if (
            isinstance(self.quoted_amount_out_raw, bool)
            or not isinstance(self.quoted_amount_out_raw, int)
            or self.quoted_amount_out_raw <= 0
        ):
            raise ValueError("quoted_amount_out_raw must be positive")

        if (
            isinstance(self.min_amount_out_raw, bool)
            or not isinstance(self.min_amount_out_raw, int)
            or self.min_amount_out_raw <= 0
        ):
            raise ValueError("min_amount_out_raw must be positive")

        if self.min_amount_out_raw > self.quoted_amount_out_raw:
            raise ValueError(
                "min_amount_out_raw cannot exceed quoted_amount_out_raw"
            )

        if not isinstance(self.projected_balances, TokenBalances):
            raise ValueError(
                "projected_balances must be a TokenBalances instance"
            )
