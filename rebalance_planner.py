"""Local rebalance planning; this module never sends transactions."""

from dataclasses import replace
from typing import Callable

from rebalance_plan import RebalancePlan
from blockchain.close_position_result import ClosePositionResult
from blockchain.balance_requirements import (
    TokenBalances,
    allocate_liquidity,
)
from blockchain.call_params import positive_amount
from blockchain.liquidity_math import estimate_swap_to_balance
from blockchain.rebalance_balances import balances_after_swap
from blockchain.slippage import minimum_amount_out
from blockchain.swap_plan import SwapPlan


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

    allocation = allocate_liquidity(
        sqrt_price_x96,
        new_lower_tick,
        new_upper_tick,
        available,
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
        required_token0_raw=allocation.required.token0_raw,
        required_token1_raw=allocation.required.token1_raw,
        planned_liquidity=allocation.liquidity,
        blocked_reason=allocation.blocked_reason,
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


def plan_swap_to_match_ratio(
    *,
    token0: str,
    token1: str,
    sqrt_price_x96: int,
    lower_tick: int,
    upper_tick: int,
    token0_balance_raw: int,
    token1_balance_raw: int,
    slippage_bps: int,
    quote: Callable[[str, str, int], int] | None = None,
) -> SwapPlan | None:
    """Return the swap that matches ``balances`` to the range ratio.

    The swap size comes from the local spot estimate
    (:func:`blockchain.liquidity_math.estimate_swap_to_balance`), which is the
    amount of the excess token. ``quote`` (QuoterV2, see
    ``blockchain.swap_router``) may replace the estimated output with an
    on-chain quote: the minimum received amount is then derived from a real
    price instead of the un-fee'd spot estimate.

    ``None`` means no swap is needed: the balances already fit the ratio or the
    estimated output is smaller than one raw unit.
    """
    balances = TokenBalances(
        token0_raw=token0_balance_raw,
        token1_raw=token1_balance_raw,
    )

    estimate = estimate_swap_to_balance(
        token0_balance_raw,
        token1_balance_raw,
        sqrt_price_x96,
        lower_tick,
        upper_tick,
    )

    if estimate is None:
        return None

    amount_in_raw = int(estimate.amount_in)

    if amount_in_raw <= 0:
        return None

    token_in_index = estimate.token_in
    token_in = token0 if token_in_index == 0 else token1
    token_out = token1 if token_in_index == 0 else token0

    amount_out_raw = (
        int(estimate.expected_amount_out)
        if quote is None
        else positive_amount(
            quote(token_in, token_out, amount_in_raw),
            "Quoted swap output",
        )
    )

    if amount_out_raw <= 0:
        return None

    return SwapPlan(
        token_in=token_in,
        token_out=token_out,
        token_in_index=token_in_index,
        amount_in_raw=amount_in_raw,
        quoted_amount_out_raw=amount_out_raw,
        min_amount_out_raw=minimum_amount_out(
            amount_out_raw,
            slippage_bps,
        ),
        projected_balances=balances_after_swap(
            balances,
            token_in_index,
            amount_in_raw,
            amount_out_raw,
        ),
    )


def build_rebalance_plan_with_swap(
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
    swap: SwapPlan | None = None,
) -> RebalancePlan:
    """Build the plan for a new position, including the ratio-fixing swap.

    ``swap`` comes from :func:`plan_swap_to_match_ratio`; the position part of
    the plan is calculated from its projected balances, which are exactly the
    balances the cycle holds once the swap is mined. This function only
    calculates a plan. It does not send transactions.
    """
    if not isinstance(close_result, ClosePositionResult):
        raise ValueError("close_result must be a ClosePositionResult")

    if swap is not None and not isinstance(swap, SwapPlan):
        raise ValueError("swap must be a SwapPlan or None")

    if swap is None:
        balances = TokenBalances(
            token0_raw=close_result.post_close_token0_balance_raw,
            token1_raw=close_result.post_close_token1_balance_raw,
        )
    else:
        balances = swap.projected_balances

    plan = build_rebalance_plan(
        network=network,
        pool_address=pool_address,
        token_id=token_id,
        current_tick=current_tick,
        old_lower_tick=old_lower_tick,
        old_upper_tick=old_upper_tick,
        new_lower_tick=new_lower_tick,
        new_upper_tick=new_upper_tick,
        sqrt_price_x96=sqrt_price_x96,
        token0_balance_raw=balances.token0_raw,
        token1_balance_raw=balances.token1_raw,
    )

    if swap is None:
        return plan

    plan = replace(
        plan,
        swap_token_in=swap.token_in,
        swap_token_out=swap.token_out,
        swap_amount_in_raw=swap.amount_in_raw,
        quoted_amount_out_raw=swap.quoted_amount_out_raw,
        min_amount_out_raw=swap.min_amount_out_raw,
        available_token0_after_swap_raw=balances.token0_raw,
        available_token1_after_swap_raw=balances.token1_raw,
    )

    plan.validate()
    return plan
