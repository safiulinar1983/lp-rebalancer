import pytest

from rebalance_plan import RebalancePlan


def make_plan(**overrides):
    data = {
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
    }
    data.update(overrides)
    return RebalancePlan(**data)


def test_requires_rebalance_when_tick_is_above_range():
    assert make_plan(current_tick=219100).requires_rebalance is True


def test_requires_rebalance_when_tick_is_below_range():
    assert make_plan(current_tick=218999).requires_rebalance is True


def test_no_rebalance_when_tick_is_inside_range():
    assert make_plan(current_tick=219050).requires_rebalance is False


def test_lower_tick_is_included_in_range():
    assert make_plan(
        current_tick=219000,
        old_lower_tick=219000,
        old_upper_tick=219100,
    ).requires_rebalance is False


def test_swap_required_for_positive_amount():
    plan = make_plan(
        swap_token_in="USDC",
        swap_token_out="WETH",
        swap_amount_in_raw=1000,
    )
    assert plan.swap_required is True


def test_swap_not_required_without_amount():
    assert make_plan().swap_required is False


def test_plan_blocked_when_gas_estimate_exceeds_limit():
    plan = make_plan(
        estimated_gas_cost_usd=0.02,
        max_gas_cost_usd=0.01,
    )
    assert plan.is_blocked is True


def test_plan_blocked_when_gas_estimate_missing_but_limit_enabled():
    plan = make_plan(max_gas_cost_usd=0.01)
    assert plan.is_blocked is True


def test_plan_not_blocked_when_gas_is_within_limit():
    plan = make_plan(
        estimated_gas_cost_usd=0.005,
        max_gas_cost_usd=0.01,
    )
    assert plan.is_blocked is False


def test_plan_blocked_by_explicit_reason():
    assert make_plan(blocked_reason="Missing quote").is_blocked is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"token_id": 0},
        {"old_lower_tick": 219100, "old_upper_tick": 219000},
        {"new_lower_tick": 219200, "new_upper_tick": 219000},
        {"token0_balance_raw": -1},
        {"token1_balance_raw": -1},
    ],
)
def test_invalid_plan_is_rejected(overrides):
    with pytest.raises(ValueError):
        make_plan(**overrides).validate()


def test_incomplete_swap_configuration_is_rejected():
    plan = make_plan(
        swap_token_in="USDC",
        swap_amount_in_raw=1000,
    )
    with pytest.raises(ValueError, match="Swap input fields"):
        plan.validate()


def test_swap_cannot_use_same_token_as_input_and_output():
    plan = make_plan(
        swap_token_in="USDC",
        swap_token_out="usdc",
        swap_amount_in_raw=1000,
    )
    with pytest.raises(ValueError, match="must differ"):
        plan.validate()


def test_minimum_output_cannot_exceed_quote():
    plan = make_plan(
        quoted_amount_out_raw=100,
        min_amount_out_raw=101,
    )
    with pytest.raises(ValueError, match="cannot exceed"):
        plan.validate()


def test_minimum_output_requires_quote():
    plan = make_plan(min_amount_out_raw=10)
    with pytest.raises(ValueError, match="requires a quote"):
        plan.validate()
