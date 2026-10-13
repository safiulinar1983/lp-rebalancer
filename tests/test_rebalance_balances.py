import pytest

from blockchain.rebalance_balances import (
    TokenBalances,
    balances_after_close,
    balances_after_swap,
)


def test_close_adds_received_tokens_to_wallet_balances():
    result = balances_after_close(
        TokenBalances(token0_raw=100, token1_raw=200),
        received_token0_raw=30,
        received_token1_raw=40,
    )
    assert result == TokenBalances(token0_raw=130, token1_raw=240)


def test_close_handles_one_sided_received_amounts():
    result = balances_after_close(
        TokenBalances(token0_raw=100, token1_raw=200),
        received_token0_raw=0,
        received_token1_raw=40,
    )
    assert result == TokenBalances(token0_raw=100, token1_raw=240)


def test_close_handles_zero_received_amounts():
    original = TokenBalances(token0_raw=100, token1_raw=200)
    assert balances_after_close(original, 0, 0) == original


@pytest.mark.parametrize("value", [-1, True, 1.5, "10"])
def test_close_rejects_invalid_received_amounts(value):
    with pytest.raises(ValueError):
        balances_after_close(TokenBalances(100, 200), value, 0)


def test_swap_token0_for_token1():
    result = balances_after_swap(
        TokenBalances(token0_raw=1000, token1_raw=500),
        token_in=0,
        amount_in_raw=300,
        amount_out_raw=275,
    )
    assert result == TokenBalances(token0_raw=700, token1_raw=775)


def test_swap_token1_for_token0():
    result = balances_after_swap(
        TokenBalances(token0_raw=1000, token1_raw=500),
        token_in=1,
        amount_in_raw=200,
        amount_out_raw=180,
    )
    assert result == TokenBalances(token0_raw=1180, token1_raw=300)


def test_swap_can_use_entire_input_balance():
    result = balances_after_swap(
        TokenBalances(token0_raw=100, token1_raw=0),
        token_in=0,
        amount_in_raw=100,
        amount_out_raw=90,
    )
    assert result == TokenBalances(token0_raw=0, token1_raw=90)


@pytest.mark.parametrize(
    ("balances", "token_in", "amount_in"),
    [
        (TokenBalances(100, 200), 0, 101),
        (TokenBalances(100, 200), 1, 201),
    ],
)
def test_swap_rejects_insufficient_input_balance(
    balances, token_in, amount_in
):
    with pytest.raises(ValueError, match="Insufficient"):
        balances_after_swap(balances, token_in, amount_in, 1)


@pytest.mark.parametrize("token_in", [-1, 2, True, 0.5])
def test_swap_rejects_invalid_token_index(token_in):
    with pytest.raises(ValueError, match="token_in"):
        balances_after_swap(TokenBalances(100, 200), token_in, 1, 1)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "10"])
def test_swap_rejects_invalid_amounts(value):
    with pytest.raises(ValueError):
        balances_after_swap(TokenBalances(100, 200), 0, value, 1)

    with pytest.raises(ValueError):
        balances_after_swap(TokenBalances(100, 200), 0, 1, value)


@pytest.mark.parametrize(
    ("token0", "token1"),
    [
        (-1, 0),
        (0, -1),
        (True, 1),
        (1, 1.5),
    ],
)
def test_token_balances_reject_invalid_values(token0, token1):
    with pytest.raises(ValueError):
        TokenBalances(token0, token1)
