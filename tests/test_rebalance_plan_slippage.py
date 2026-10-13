import pytest

from rebalance_plan import RebalancePlan


def make_plan(**overrides):
    values = {
        "network": "base_sepolia",
        "pool_address": "0x1234",
        "token_id": 82740,
        "current_tick": 219103,
        "old_lower_tick": 219000,
        "old_upper_tick": 219100,
        "new_lower_tick": 219000,
        "new_upper_tick": 219200,
        "token0_balance_raw": 1_000_000,
        "token1_balance_raw": 100_000,
        "swap_token_in": "USDC",
        "swap_token_out": "WETH",
        "swap_amount_in_raw": 1000,
        "quoted_amount_out_raw": 2000,
        "min_amount_out_raw": 1990,
    }
    values.update(overrides)
    return RebalancePlan(**values)


def test_valid_swap_plan_passes_validation():
    make_plan().validate()


def test_swap_requires_quote():
    with pytest.raises(ValueError, match="Swap requires a quoted output"):
        make_plan(quoted_amount_out_raw=None).validate()


def test_swap_requires_minimum_output():
    with pytest.raises(ValueError, match="Swap requires a minimum output"):
        make_plan(min_amount_out_raw=None).validate()


@pytest.mark.parametrize("value", [0, -1])
def test_quote_must_be_positive(value):
    with pytest.raises(ValueError, match="Quoted output must be positive"):
        make_plan(quoted_amount_out_raw=value).validate()


@pytest.mark.parametrize("value", [0, -1])
def test_minimum_output_must_be_positive(value):
    with pytest.raises(ValueError, match="Minimum output must be positive"):
        make_plan(min_amount_out_raw=value).validate()


def test_minimum_output_cannot_exceed_quote():
    with pytest.raises(ValueError, match="cannot exceed"):
        make_plan(
            quoted_amount_out_raw=100,
            min_amount_out_raw=101,
        ).validate()


def test_plan_without_swap_needs_no_quote():
    make_plan(
        swap_token_in=None,
        swap_token_out=None,
        swap_amount_in_raw=None,
        quoted_amount_out_raw=None,
        min_amount_out_raw=None,
    ).validate()
