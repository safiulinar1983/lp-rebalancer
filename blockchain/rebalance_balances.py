"""Pure balance calculations for LP rebalancing.

This module does not read the blockchain or submit transactions.
All amounts are integer raw token units.
"""

from blockchain.token_balances import TokenBalances

__all__ = [
    "TokenBalances",
    "balances_after_close",
    "balances_after_swap",
]


def _validate_amount(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")


def _validate_positive_amount(value: int, name: str) -> None:
    _validate_amount(value, name)
    if value == 0:
        raise ValueError(f"{name} must be positive")


def balances_after_close(
    wallet_balances_before_close: TokenBalances,
    received_token0_raw: int,
    received_token1_raw: int,
) -> TokenBalances:
    """Project balances after collecting tokens from a closed position.

    received_token*_raw should represent the actual or explicitly estimated
    amounts received from the position close and collection. Do not pass
    amounts already included in wallet_balances_before_close.
    """
    _validate_amount(received_token0_raw, "received_token0_raw")
    _validate_amount(received_token1_raw, "received_token1_raw")

    return TokenBalances(
        token0_raw=(
            wallet_balances_before_close.token0_raw
            + received_token0_raw
        ),
        token1_raw=(
            wallet_balances_before_close.token1_raw
            + received_token1_raw
        ),
    )


def balances_after_swap(
    balances: TokenBalances,
    token_in: int,
    amount_in_raw: int,
    amount_out_raw: int,
) -> TokenBalances:
    """Project balances using the actual or simulated swap amounts.

    token_in=0 means token0 is sold for token1.
    token_in=1 means token1 is sold for token0.

    This function does not execute a swap or obtain a quote.
    """
    if isinstance(token_in, bool) or token_in not in (0, 1):
        raise ValueError("token_in must be 0 or 1")

    _validate_positive_amount(amount_in_raw, "amount_in_raw")
    _validate_positive_amount(amount_out_raw, "amount_out_raw")

    if token_in == 0:
        if amount_in_raw > balances.token0_raw:
            raise ValueError("Insufficient token0 balance for swap")

        return TokenBalances(
            token0_raw=balances.token0_raw - amount_in_raw,
            token1_raw=balances.token1_raw + amount_out_raw,
        )

    if amount_in_raw > balances.token1_raw:
        raise ValueError("Insufficient token1 balance for swap")

    return TokenBalances(
        token0_raw=balances.token0_raw + amount_out_raw,
        token1_raw=balances.token1_raw - amount_in_raw,
    )
