from decimal import Decimal

import pytest

from blockchain.balance_requirements import (
    TokenBalances,
    check_sufficient_balances,
    required_token_amounts,
)
from blockchain.liquidity_math import Q96, amounts_per_liquidity


def test_sufficient_balances():
    available = TokenBalances(120, 250)
    required = TokenBalances(100, 200)

    result = check_sufficient_balances(available, required)

    assert result.sufficient
    assert result.deficit == TokenBalances(0, 0)


def test_insufficient_balances_report_each_deficit():
    result = check_sufficient_balances(
        TokenBalances(90, 250),
        TokenBalances(100, 300),
    )

    assert not result.sufficient
    assert result.deficit == TokenBalances(10, 50)


def test_surplus_in_one_token_does_not_hide_other_token_deficit():
    result = check_sufficient_balances(
        TokenBalances(10_000, 20),
        TokenBalances(100, 30),
    )

    assert not result.sufficient
    assert result.deficit == TokenBalances(0, 10)


def test_required_amounts_match_liquidity_math_and_round_up():
    lower_tick, upper_tick = -100, 100
    sqrt_price_x96 = int(Q96)
    liquidity = 1_000_000

    per_liquidity = amounts_per_liquidity(
        Decimal(1), lower_tick, upper_tick
    )
    required = required_token_amounts(
        sqrt_price_x96, lower_tick, upper_tick, liquidity
    )

    assert required.token0_raw >= per_liquidity.amount0 * liquidity
    assert required.token1_raw >= per_liquidity.amount1 * liquidity
    assert required.token0_raw - per_liquidity.amount0 * liquidity < 1
    assert required.token1_raw - per_liquidity.amount1 * liquidity < 1


def test_out_of_range_requirement_can_be_one_sided():
    below_range = required_token_amounts(
        int(Q96), 100, 200, 1_000_000
    )

    assert below_range.token0_raw > 0
    assert below_range.token1_raw == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sqrt_price_x96": 0, "lower_tick": -10, "upper_tick": 10, "liquidity": 1},
        {"sqrt_price_x96": int(Q96), "lower_tick": -10, "upper_tick": 10, "liquidity": 0},
        {"sqrt_price_x96": int(Q96), "lower_tick": -10, "upper_tick": 10, "liquidity": -1},
        {"sqrt_price_x96": int(Q96), "lower_tick": 10, "upper_tick": -10, "liquidity": 1},
    ],
)
def test_invalid_requirement_inputs_raise(kwargs):
    with pytest.raises(ValueError):
        required_token_amounts(**kwargs)


@pytest.mark.parametrize(
    "balances",
    [
        (-1, 0),
        (0, -1),
        (True, 0),
        (0, 1.5),
    ],
)
def test_invalid_balances_raise(balances):
    with pytest.raises(ValueError):
        TokenBalances(*balances)


def test_wrong_balance_argument_type_raises():
    with pytest.raises(TypeError):
        check_sufficient_balances((100, 100), TokenBalances(50, 50))
