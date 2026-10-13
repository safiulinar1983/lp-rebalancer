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
        "token0_balance_raw": 1_000,
        "token1_balance_raw": 500,
    }
    values.update(overrides)
    return RebalancePlan(**values)


def test_plan_without_requirements_keeps_existing_behavior():
    plan = make_plan()
    plan.validate()
    assert not plan.is_blocked
    assert plan.balance_check_reason is None


def test_sufficient_current_balances_are_not_blocked():
    plan = make_plan(
        required_token0_raw=900,
        required_token1_raw=450,
    )
    plan.validate()
    assert not plan.is_blocked
    assert plan.balance_check_reason is None


def test_insufficient_token0_blocks_plan():
    plan = make_plan(
        required_token0_raw=1_001,
        required_token1_raw=400,
    )
    plan.validate()
    assert plan.is_blocked
    assert "Insufficient token0 balance" in plan.balance_check_reason


def test_insufficient_token1_blocks_plan():
    plan = make_plan(
        required_token0_raw=900,
        required_token1_raw=501,
    )
    plan.validate()
    assert plan.is_blocked
    assert "Insufficient token1 balance" in plan.balance_check_reason


def test_both_token_deficits_are_reported():
    plan = make_plan(
        required_token0_raw=1_001,
        required_token1_raw=501,
    )
    assert plan.is_blocked
    assert "Insufficient token0 balance" in plan.balance_check_reason
    assert "Insufficient token1 balance" in plan.balance_check_reason


def test_swap_plan_without_projected_balances_is_blocked():
    plan = make_plan(
        swap_token_in="USDC",
        swap_token_out="WETH",
        swap_amount_in_raw=100,
        quoted_amount_out_raw=200,
        min_amount_out_raw=190,
        required_token0_raw=900,
        required_token1_raw=450,
    )
    plan.validate()
    assert plan.is_blocked
    assert "Post-swap balances are required" in plan.balance_check_reason


def test_sufficient_projected_balances_allow_plan():
    plan = make_plan(
        swap_token_in="USDC",
        swap_token_out="WETH",
        swap_amount_in_raw=100,
        quoted_amount_out_raw=200,
        min_amount_out_raw=190,
        required_token0_raw=850,
        required_token1_raw=600,
        available_token0_after_swap_raw=900,
        available_token1_after_swap_raw=650,
    )
    plan.validate()
    assert not plan.is_blocked
    assert plan.balance_check_reason is None


def test_insufficient_projected_balances_block_swap_plan():
    plan = make_plan(
        swap_token_in="USDC",
        swap_token_out="WETH",
        swap_amount_in_raw=100,
        quoted_amount_out_raw=200,
        min_amount_out_raw=190,
        required_token0_raw=950,
        required_token1_raw=600,
        available_token0_after_swap_raw=900,
        available_token1_after_swap_raw=650,
    )
    plan.validate()
    assert plan.is_blocked
    assert "Insufficient token0 balance" in plan.balance_check_reason


def test_required_amounts_must_be_provided_together():
    plan = make_plan(required_token0_raw=100)
    with pytest.raises(ValueError, match="provided together"):
        plan.validate()


@pytest.mark.parametrize("value", [-1, -100])
def test_negative_required_amounts_are_rejected(value):
    plan = make_plan(
        required_token0_raw=value,
        required_token1_raw=100,
    )
    with pytest.raises(ValueError, match="cannot be negative"):
        plan.validate()


def test_projected_balances_must_be_provided_together():
    plan = make_plan(available_token0_after_swap_raw=100)
    with pytest.raises(ValueError, match="provided together"):
        plan.validate()


def test_negative_projected_balances_are_rejected():
    plan = make_plan(
        available_token0_after_swap_raw=-1,
        available_token1_after_swap_raw=100,
    )
    with pytest.raises(ValueError, match="cannot be negative"):
        plan.validate()
