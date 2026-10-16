"""Shared raw token balance value object.

A single definition is used by every module that works with wallet assets so
that validation rules cannot drift apart.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenBalances:
    """Token balances in raw units, such as USDC micro-units and WETH wei."""

    token0_raw: int
    token1_raw: int

    def __post_init__(self) -> None:
        for name, value in (
            ("token0_raw", self.token0_raw),
            ("token1_raw", self.token1_raw),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
