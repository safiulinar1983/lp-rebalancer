"""Local rebalance planning; this module never sends transactions."""

from rebalance_plan import RebalancePlan
from blockchain.close_position_result import ClosePositionResult
from blockchain.balance_requirements import (
    TokenBalances,
    max_liquidity_for_balances,
    required_token_amounts,
)


def build_rebalance_plan(
    *,
    network: str,
    pool_address: str,
    token_id: int,
    current_tick: int,
    old_lower_tick: int,
    old_upper_tick: int,
    new_lower_tick: int,
    new_upper_tick: int,
    sqrt_price_x96: int,
    token0_balance_raw: int,
    token1_balance_raw: int,
) -> RebalancePlan:
    """Calculate affordable liquidity and token requirements from raw balances."""
    available = TokenBalances(
        token0_raw=token0_balance_raw,
        token1_raw=token1_balance_raw,
    )

    liquidity = max_liquidity_for_balances(
        sqrt_price_x96,
        new_lower_tick,
        new_upper_tick,
        available,
    )

    def calculate_requirements(value: int):
        return required_token_amounts(
            sqrt_price_x96,
            new_lower_tick,
            new_upper_tick,
            value,
        )

    required = (
        calculate_requirements(liquidity)
        if liquidity > 0
        else TokenBalances(token0_raw=0, token1_raw=0)
    )

    # Verify feasibility after the token amounts have been rounded up.
    if liquidity > 0 and (
        required.token0_raw > token0_balance_raw
        or required.token1_raw > token1_balance_raw
    ):
        low, high = 0, liquidity
        while low < high:
            middle = (low + high + 1) // 2
            candidate = calculate_requirements(middle)
            if (
                candidate.token0_raw <= token0_balance_raw
                and candidate.token1_raw <= token1_balance_raw
            ):
                low = middle
            else:
                high = middle - 1

        liquidity = low
        required = (
            calculate_requirements(liquidity)
            if liquidity > 0
            else TokenBalances(token0_raw=0, token1_raw=0)
        )

    blocked_reason = None
    if liquidity == 0:
        blocked_reason = (
            "Available balances cannot fund positive liquidity in the target range"
        )

    plan = RebalancePlan(
        network=network,
        pool_address=pool_address,
        token_id=token_id,
        current_tick=current_tick,
        old_lower_tick=old_lower_tick,
        old_upper_tick=old_upper_tick,
        new_lower_tick=new_lower_tick,
        new_upper_tick=new_upper_tick,
        token0_balance_raw=token0_balance_raw,
        token1_balance_raw=token1_balance_raw,
        required_token0_raw=required.token0_raw,
        required_token1_raw=required.token1_raw,
        planned_liquidity=liquidity,
        blocked_reason=blocked_reason,
    )
    plan.validate()
    return plan


def build_rebalance_plan_after_close(
    *,
    close_result: ClosePositionResult,
    network: str,
    pool_address: str,
    token_id: int,
    current_tick: int,
    old_lower_tick: int,
    old_upper_tick: int,
    new_lower_tick: int,
    new_upper_tick: int,
    sqrt_price_x96: int,
) -> RebalancePlan:
    """Build a local rebalance plan using projected post-close balances.

    This function only calculates a plan. It does not send transactions.
    """
    if not isinstance(close_result, ClosePositionResult):
        raise ValueError("close_result must be a ClosePositionResult")

    return build_rebalance_plan(
        network=network,
        pool_address=pool_address,
        token_id=token_id,
        current_tick=current_tick,
        old_lower_tick=old_lower_tick,
        old_upper_tick=old_upper_tick,
        new_lower_tick=new_lower_tick,
        new_upper_tick=new_upper_tick,
        sqrt_price_x96=sqrt_price_x96,
        token0_balance_raw=close_result.post_close_token0_balance_raw,
        token1_balance_raw=close_result.post_close_token1_balance_raw,
    )
