"""Decode simulated PancakeSwap V3 position-close results.

This module performs local calculations only. It never sends transactions.
"""

from dataclasses import dataclass

from eth_abi import decode


@dataclass(frozen=True)
class ClosePositionResult:
    """Decoded amounts in raw token units."""

    decreased_amount0_raw: int
    decreased_amount1_raw: int
    collected_amount0_raw: int
    collected_amount1_raw: int
    post_close_token0_balance_raw: int
    post_close_token1_balance_raw: int


def _validate_raw_amount(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")


def decode_decrease_and_collect_results(
    results: list[bytes] | tuple[bytes, ...],
    *,
    token0_balance_raw: int = 0,
    token1_balance_raw: int = 0,
) -> ClosePositionResult:
    """Decode decreaseLiquidity + collect results from multicall.

    ``results[0]`` is the return data from decreaseLiquidity.
    ``results[1]`` is the return data from collect.

    The collected amounts already include the tokens collected after the
    liquidity decrease, plus any previously owed tokens that were collected.
    Therefore, only the collected amounts are added to wallet balances.
    """
    _validate_raw_amount(token0_balance_raw, "token0_balance_raw")
    _validate_raw_amount(token1_balance_raw, "token1_balance_raw")

    if not isinstance(results, (list, tuple)) or len(results) != 2:
        raise ValueError("Expected exactly two multicall results")

    decoded_amounts = []
    for index, result in enumerate(results):
        if not isinstance(result, (bytes, bytearray, memoryview)):
            raise ValueError(f"Multicall result {index} must be bytes")
        try:
            values = decode(["uint256", "uint256"], bytes(result))
        except Exception as exc:
            raise ValueError(
                f"Could not decode multicall result {index}"
            ) from exc
        decoded_amounts.append((int(values[0]), int(values[1])))

    decreased0, decreased1 = decoded_amounts[0]
    collected0, collected1 = decoded_amounts[1]

    return ClosePositionResult(
        decreased_amount0_raw=decreased0,
        decreased_amount1_raw=decreased1,
        collected_amount0_raw=collected0,
        collected_amount1_raw=collected1,
        post_close_token0_balance_raw=token0_balance_raw + collected0,
        post_close_token1_balance_raw=token1_balance_raw + collected1,
    )
