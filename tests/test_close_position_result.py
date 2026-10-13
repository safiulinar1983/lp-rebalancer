import pytest
from eth_abi import encode

from blockchain.close_position_result import (
    ClosePositionResult,
    decode_decrease_and_collect_results,
)


def encoded_amounts(amount0: int, amount1: int) -> bytes:
    return encode(["uint256", "uint256"], [amount0, amount1])


def test_decodes_close_results_and_adds_collected_amounts():
    results = [
        encoded_amounts(1_000, 2_000),
        encoded_amounts(1_100, 2_200),
    ]

    result = decode_decrease_and_collect_results(
        results,
        token0_balance_raw=500,
        token1_balance_raw=700,
    )

    assert result == ClosePositionResult(
        decreased_amount0_raw=1_000,
        decreased_amount1_raw=2_000,
        collected_amount0_raw=1_100,
        collected_amount1_raw=2_200,
        post_close_token0_balance_raw=1_600,
        post_close_token1_balance_raw=2_900,
    )


def test_zero_collected_amounts_are_supported():
    result = decode_decrease_and_collect_results(
        [encoded_amounts(0, 0), encoded_amounts(0, 0)]
    )

    assert result.post_close_token0_balance_raw == 0
    assert result.post_close_token1_balance_raw == 0


@pytest.mark.parametrize("results", [[], [encoded_amounts(1, 2)]])
def test_rejects_wrong_number_of_results(results):
    with pytest.raises(ValueError, match="exactly two"):
        decode_decrease_and_collect_results(results)


def test_rejects_malformed_encoded_result():
    with pytest.raises(ValueError, match="Could not decode"):
        decode_decrease_and_collect_results([b"bad", encoded_amounts(0, 0)])


def test_rejects_negative_initial_balance():
    with pytest.raises(ValueError, match="cannot be negative"):
        decode_decrease_and_collect_results(
            [encoded_amounts(0, 0), encoded_amounts(0, 0)],
            token0_balance_raw=-1,
        )


def test_rejects_boolean_initial_balance():
    with pytest.raises(ValueError, match="must be an integer"):
        decode_decrease_and_collect_results(
            [encoded_amounts(0, 0), encoded_amounts(0, 0)],
            token1_balance_raw=True,
        )
