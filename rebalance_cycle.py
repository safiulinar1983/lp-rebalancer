"""Execution of one LP rebalancing cycle.

A cycle turns a strategy decision into the steps a position needs:

* ``COLLECT_FEES``: collect the fees and put them back to work in the same NFT
  with ``increaseLiquidity``, swapping part of them first when the collected
  amounts do not match the position ratio;
* ``REBALANCE``: close the position (``decreaseLiquidity`` + ``collect``),
  optionally burn the emptied NFT, swap to match the new range ratio and mint a
  new position.

``DRY_RUN`` never signs anything. Steps whose tokens already exist on chain
(``approve``, ``collect``, ``close_position``) are verified through ``eth_call``
and reported as ``simulated``. Steps that spend tokens produced by earlier steps
(``swap``, ``increaseLiquidity``, ``mint``) cannot be verified before those
tokens exist, so they are reported as ``prepared`` instead of pretending to be
simulated.

``LIVE`` sends every step with ``blockchain.tx.send_transaction`` after the gas
budget of the whole cycle has been checked.

The module never reads configuration or environment variables: account,
adapters, prices and store are injected by the caller, see
``scripts/rebalance.py``.
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Callable

from web3 import Web3
from web3.contract.contract import ContractFunction

from config import AppConfig, MODE_LIVE
from strategy import Strategy, StrategyDecision
from rebalance_plan import RebalancePlan
from blockchain.close_position_result import (
    ClosePositionResult,
    decode_decrease_and_collect_results,
)
from blockchain.erc20 import ERC20Token
from blockchain.fees import calculate_fees_value_usd
from blockchain.gas import (
    check_gas_budget,
    gas_limit_for,
    resolve_native_token_price_usd,
)
from blockchain.interfaces import PoolAdapter
from blockchain.pancake_v3 import PoolState
from blockchain.position_manager import PositionManager
from blockchain.positions import Position
from blockchain.slippage import slippage_floor
from blockchain.swap_plan import SwapPlan
from blockchain.swap_router import SwapRouter
from blockchain.token_balances import TokenBalances
from blockchain.tx import send_transaction, simulate
from rebalance_planner import (
    build_rebalance_plan_with_swap,
    plan_swap_to_match_ratio,
)

# Step statuses: what happened to one step of the cycle.
STEP_SENT = "sent"
STEP_SIMULATED = "simulated"
STEP_PREPARED = "prepared"


@dataclass(frozen=True)
class CycleStep:
    """One step of the cycle with the status it reached."""

    name: str
    detail: str
    status: str
    tx_hash: str | None = None

    def __post_init__(self) -> None:
        if self.status not in (STEP_SENT, STEP_SIMULATED, STEP_PREPARED):
            raise ValueError(f"Unknown step status: {self.status}")

        if self.status == STEP_SENT and not self.tx_hash:
            raise ValueError("A sent step must carry its transaction hash")

        if self.status != STEP_SENT and self.tx_hash:
            raise ValueError("Only sent steps carry a transaction hash")

    @property
    def sent(self) -> bool:
        """Whether the step was actually broadcast."""
        return self.status == STEP_SENT


@dataclass(frozen=True)
class CycleResult:
    """Outcome of one cycle: what was decided and what was done about it."""

    mode: str
    action: str
    steps: tuple[CycleStep, ...] = ()
    plan: RebalancePlan | None = None
    swap: SwapPlan | None = None
    blocked_reason: str | None = None
    new_token_id: int | None = None

    @property
    def blocked(self) -> bool:
        """Whether the cycle refused to touch the chain."""
        return self.blocked_reason is not None

    @property
    def sent_steps(self) -> tuple[CycleStep, ...]:
        """The steps that were broadcast."""
        return tuple(step for step in self.steps if step.sent)


def format_cycle_result(result: CycleResult) -> str:
    """Render a human-readable cycle report (CLI output is print-based)."""
    lines = [
        "=" * 50,
        "LP REBALANCE CYCLE",
        "=" * 50,
        f"Mode:          {result.mode}",
        f"Action:        {result.action}",
    ]

    if result.new_token_id is not None:
        lines.append(f"New LP NFT:    #{result.new_token_id}")

    if result.blocked_reason:
        lines.append(f"Blocked:       {result.blocked_reason}")

    lines.append("")

    if not result.steps:
        lines.append("No steps required.")

    for index, step in enumerate(result.steps, start=1):
        lines.append(f"{index}. {step.name} [{step.status}] {step.detail}")

        if step.tx_hash:
            lines.append(f"   tx: {step.tx_hash}")

    plan = result.plan

    if plan is not None:
        available0 = plan.available_token0_after_swap_raw
        available1 = plan.available_token1_after_swap_raw

        lines.append("")
        lines.append(f"Current tick:  {plan.current_tick}")
        lines.append(
            f"Old range:     {plan.old_lower_tick}..{plan.old_upper_tick}"
        )
        lines.append(
            f"New range:     {plan.new_lower_tick}..{plan.new_upper_tick}"
        )
        lines.append(f"Liquidity:     {plan.planned_liquidity}")
        lines.append(
            f"Required:      {plan.required_token0_raw} / "
            f"{plan.required_token1_raw} raw units"
        )
        lines.append(
            f"Available:     {available0} / {available1} raw units"
        )

        if plan.estimated_gas_cost_usd is not None:
            lines.append(
                f"Gas estimate:  ${plan.estimated_gas_cost_usd:.6f}"
            )

    swap = result.swap

    if swap is not None:
        lines.append("")
        lines.append(
            f"Swap:          {swap.amount_in_raw} raw units of {swap.token_in}"
        )
        lines.append(
            f"Swap output:   min {swap.min_amount_out_raw} raw units of "
            f"{swap.token_out}"
        )

    lines.append("=" * 50)
    return "\n".join(lines)


class RebalanceCycle:
    """Plan and (in LIVE mode) execute one cycle for a single LP position."""

    def __init__(
        self,
        *,
        w3: Web3,
        config: AppConfig,
        pool: PoolAdapter,
        position_manager: PositionManager,
        strategy: Strategy,
        token0_price_usd: Decimal,
        token1_price_usd: Decimal,
        swap_router: SwapRouter | None = None,
        account: Any | None = None,
        store: Any | None = None,
        token_factory: Callable[[str], ERC20Token] | None = None,
    ):
        if config.mode == MODE_LIVE and account is None:
            raise ValueError(
                "LIVE mode requires an unlocked account "
                "(set PRIVATE_KEY in .env)"
            )

        self.w3 = w3
        self.config = config
        self.pool = pool
        self.position_manager = position_manager
        self.strategy = strategy
        self.token0_price_usd = token0_price_usd
        self.token1_price_usd = token1_price_usd
        self.swap_router = swap_router
        self.account = account
        self.store = store
        self._token_factory = token_factory or (
            lambda address: ERC20Token(w3, address)
        )

    @property
    def live(self) -> bool:
        """Whether the cycle sends transactions instead of simulating them."""
        return self.config.mode == MODE_LIVE

    @property
    def can_quote(self) -> bool:
        """Whether an on-chain swap quote is available."""
        return self.swap_router is not None and self.swap_router.can_quote

    def run(self) -> CycleResult:
        """Evaluate the position and hold, compound or rebalance it."""
        state = self.pool.read_state()

        position = self.position_manager.find_position(
            token0=state.token0,
            token1=state.token1,
            fee=state.fee,
            token_id=self.config.position_token_id,
        )

        # Read through eth_call: the monitor and the strategy need the fees
        # before anything is sent.
        amount0_raw, amount1_raw = (
            self.position_manager.simulate_collect_fees(position.token_id)
        )

        fees_value_usd = calculate_fees_value_usd(
            amount0_raw,
            amount1_raw,
            state.token0_decimals,
            state.token1_decimals,
            self.token0_price_usd,
            self.token1_price_usd,
        )

        decision = self.strategy.evaluate(
            state,
            position,
            fees_value_usd=fees_value_usd,
        )

        if decision.action == "COLLECT_FEES":
            result = self._compound(
                state,
                position,
                amount0_raw,
                amount1_raw,
            )
        elif decision.action == "REBALANCE":
            result = self._rebalance(state, position, decision)
        else:
            result = CycleResult(
                mode=self.config.mode,
                action=decision.action,
            )

        self._record(
            result,
            state=state,
            position=position,
            decision=decision,
            fees_value_usd=fees_value_usd,
        )

        return result

    def _compound(
        self,
        state: PoolState,
        position: Position,
        amount0_raw: int,
        amount1_raw: int,
    ) -> CycleResult:
        """Collect the fees and put them back to work in the same NFT."""
        steps: list[CycleStep] = [
            self._send_or_simulate(
                "collect",
                self.position_manager.build_collect(position.token_id),
                detail=(
                    f"collect owed fees of LP NFT #{position.token_id} "
                    f"({amount0_raw}/{amount1_raw} raw units)"
                ),
            )
        ]

        swap = self._plan_swap(
            state=state,
            lower_tick=position.lower_tick,
            upper_tick=position.upper_tick,
            token0_balance_raw=amount0_raw,
            token1_balance_raw=amount1_raw,
        )

        if swap is None:
            balances = TokenBalances(
                token0_raw=amount0_raw,
                token1_raw=amount1_raw,
            )
        else:
            balances = swap.projected_balances
            steps.extend(self._swap_steps(state, swap))

        if balances.token0_raw == 0 and balances.token1_raw == 0:
            return CycleResult(
                mode=self.config.mode,
                action="COLLECT_FEES",
                steps=tuple(steps),
                swap=swap,
                blocked_reason="Collected fees are too small to compound",
            )

        steps.extend(
            self._approval_steps(
                state.token0,
                self.position_manager.address,
                balances.token0_raw,
            )
        )
        steps.extend(
            self._approval_steps(
                state.token1,
                self.position_manager.address,
                balances.token1_raw,
            )
        )

        steps.append(
            self._send_or_prepare(
                "increase_liquidity",
                self.position_manager.build_increase_liquidity(
                    position.token_id,
                    balances.token0_raw,
                    balances.token1_raw,
                    slippage_floor(
                        balances.token0_raw,
                        self.config.slippage_bps,
                    ),
                    slippage_floor(
                        balances.token1_raw,
                        self.config.slippage_bps,
                    ),
                ),
                detail=(
                    f"compound {balances.token0_raw}/"
                    f"{balances.token1_raw} raw units of fees into LP NFT "
                    f"#{position.token_id}"
                ),
            )
        )

        return CycleResult(
            mode=self.config.mode,
            action="COLLECT_FEES",
            steps=tuple(steps),
            swap=swap,
        )

    def _rebalance(
        self,
        state: PoolState,
        position: Position,
        decision: StrategyDecision,
    ) -> CycleResult:
        """Close the position, swap the excess token and mint a new one."""
        if (
            decision.proposed_lower_tick is None
            or decision.proposed_upper_tick is None
        ):
            raise ValueError("REBALANCE decision must provide a new range")

        known_token_ids = (
            set(self.position_manager.get_token_ids()) if self.live else set()
        )

        wallet_balances = TokenBalances(
            token0_raw=self._token_factory(state.token0).balance_of(
                self.config.wallet_address
            ),
            token1_raw=self._token_factory(state.token1).balance_of(
                self.config.wallet_address
            ),
        )

        close_result = self._simulate_close(position, wallet_balances)

        swap = self._plan_swap(
            state=state,
            lower_tick=decision.proposed_lower_tick,
            upper_tick=decision.proposed_upper_tick,
            token0_balance_raw=close_result.post_close_token0_balance_raw,
            token1_balance_raw=close_result.post_close_token1_balance_raw,
        )

        plan = build_rebalance_plan_with_swap(
            close_result=close_result,
            swap=swap,
            network=self.config.network,
            pool_address=self.config.pool_address,
            token_id=position.token_id,
            current_tick=state.tick,
            old_lower_tick=position.lower_tick,
            old_upper_tick=position.upper_tick,
            new_lower_tick=decision.proposed_lower_tick,
            new_upper_tick=decision.proposed_upper_tick,
            sqrt_price_x96=state.sqrt_price_x96,
        )

        if plan.swap_required and self.live and not self.can_quote:
            plan = replace(
                plan,
                blocked_reason=(
                    "LIVE mode requires an on-chain swap quote: "
                    "configure quoter.address"
                ),
            )

        plan, gas_reason = self._apply_gas_budget(state, plan)

        if plan.is_blocked:
            reason = (
                plan.blocked_reason
                or plan.balance_check_reason
                or gas_reason
                or "Rebalance plan exceeds the configured gas budget"
            )

            return CycleResult(
                mode=self.config.mode,
                action="REBALANCE",
                plan=plan,
                swap=swap,
                blocked_reason=reason,
            )

        steps = self._rebalance_steps(
            state,
            position,
            plan,
            swap,
            close_result,
        )

        new_token_id = (
            self._read_new_token_id(known_token_ids) if self.live else None
        )

        return CycleResult(
            mode=self.config.mode,
            action="REBALANCE",
            steps=steps,
            plan=plan,
            swap=swap,
            new_token_id=new_token_id,
        )

    def _rebalance_steps(
        self,
        state: PoolState,
        position: Position,
        plan: RebalancePlan,
        swap: SwapPlan | None,
        close_result: ClosePositionResult,
    ) -> tuple[CycleStep, ...]:
        """Run (LIVE) or prepare (DRY_RUN) the rebalance steps in order."""
        steps: list[CycleStep] = [
            self._send_or_simulate(
                "close_position",
                self.position_manager.build_close_position(
                    position.token_id,
                    position.liquidity,
                ),
                detail=(
                    f"close LP NFT #{position.token_id}: decrease "
                    f"{position.liquidity} liquidity and collect "
                    f"{close_result.collected_amount0_raw}/"
                    f"{close_result.collected_amount1_raw} raw units"
                ),
            )
        ]

        if self.config.burn_closed_position:
            steps.append(
                self._send_or_simulate(
                    "burn",
                    self.position_manager.build_burn(position.token_id),
                    detail=f"burn emptied LP NFT #{position.token_id}",
                )
            )

        if swap is not None:
            steps.extend(self._swap_steps(state, swap))

        steps.extend(self._mint_steps(state, plan))

        return tuple(steps)

    def _mint_steps(
        self,
        state: PoolState,
        plan: RebalancePlan,
    ) -> list[CycleStep]:
        """Return the approvals and the mint call for the planned position."""
        amount0_raw = plan.required_token0_raw
        amount1_raw = plan.required_token1_raw

        if amount0_raw is None or amount1_raw is None:
            raise RuntimeError("Rebalance plan is missing token requirements")

        steps: list[CycleStep] = []
        steps.extend(
            self._approval_steps(
                state.token0,
                self.position_manager.address,
                amount0_raw,
            )
        )
        steps.extend(
            self._approval_steps(
                state.token1,
                self.position_manager.address,
                amount1_raw,
            )
        )

        steps.append(
            self._send_or_prepare(
                "mint",
                self.position_manager.build_mint(
                    token0=state.token0,
                    token1=state.token1,
                    fee=state.fee,
                    tick_lower=plan.new_lower_tick,
                    tick_upper=plan.new_upper_tick,
                    amount0_desired=amount0_raw,
                    amount1_desired=amount1_raw,
                    amount0_min=slippage_floor(
                        amount0_raw,
                        self.config.slippage_bps,
                    ),
                    amount1_min=slippage_floor(
                        amount1_raw,
                        self.config.slippage_bps,
                    ),
                ),
                detail=(
                    f"mint a new position in {plan.new_lower_tick}.."
                    f"{plan.new_upper_tick} with {amount0_raw}/"
                    f"{amount1_raw} raw units"
                ),
            )
        )

        return steps

    def _swap_steps(
        self,
        state: PoolState,
        swap: SwapPlan,
    ) -> list[CycleStep]:
        """Return the approval and swap steps that sell the excess token."""
        detail = (
            f"swap {swap.amount_in_raw} raw units of {swap.token_in} for at "
            f"least {swap.min_amount_out_raw} raw units of {swap.token_out}"
        )

        if not self.live:
            source = (
                "the on-chain quote"
                if self.can_quote
                else "the local spot estimate"
            )

            return [
                CycleStep(
                    name="swap",
                    detail=f"{detail} (prepared from {source})",
                    status=STEP_PREPARED,
                )
            ]

        if self.swap_router is None:
            raise RuntimeError("LIVE swap requires swap_router.address")

        steps = self._approval_steps(
            swap.token_in,
            self.swap_router.address,
            swap.amount_in_raw,
        )

        steps.append(
            self._send_or_prepare(
                "swap",
                self.swap_router.build_exact_input_single(
                    swap.token_in,
                    swap.token_out,
                    state.fee,
                    self.config.wallet_address,
                    swap.amount_in_raw,
                    swap.min_amount_out_raw,
                ),
                detail=detail,
            )
        )

        return steps

    def _approval_steps(
        self,
        token: str,
        spender: str,
        amount_raw: int,
    ) -> list[CycleStep]:
        """Return the approve step needed before ``spender`` pulls tokens."""
        if amount_raw <= 0:
            return []

        erc20 = self._token_factory(token)

        if not erc20.needs_approval(
            self.config.wallet_address,
            spender,
            amount_raw,
        ):
            return []

        spender_label = (
            "position manager"
            if spender.lower() == self.position_manager.address.lower()
            else "swap router"
        )

        return [
            self._send_or_simulate(
                "approve",
                erc20.build_approve(spender, amount_raw),
                detail=(
                    f"approve {amount_raw} raw units of {token} for the "
                    f"{spender_label}"
                ),
            )
        ]

    def _send_or_simulate(
        self,
        name: str,
        function_call: ContractFunction,
        *,
        detail: str,
    ) -> CycleStep:
        """Send the step in LIVE mode, verify it with eth_call in DRY_RUN.

        Only steps that do not depend on tokens produced by earlier steps can
        be verified this way: their preconditions are already on chain.
        """
        if not self.live:
            simulate(function_call, self.config.wallet_address)

            return CycleStep(
                name=name,
                detail=f"{detail} (verified through eth_call)",
                status=STEP_SIMULATED,
            )

        receipt = send_transaction(
            self.w3,
            self.account,
            function_call,
            gas_limit=gas_limit_for(name),
        )

        return CycleStep(
            name=name,
            detail=detail,
            status=STEP_SENT,
            tx_hash=receipt.tx_hash,
        )

    def _send_or_prepare(
        self,
        name: str,
        function_call: ContractFunction,
        *,
        detail: str,
    ) -> CycleStep:
        """Send the step in LIVE mode, or report the prepared call in DRY_RUN.

        The calldata is built in both modes, so its arguments are validated
        locally even when eth_call cannot succeed yet: the tokens the call
        spends only exist after the earlier steps are mined.
        """
        if not self.live:
            return CycleStep(
                name=name,
                detail=f"{detail} (calldata validated locally)",
                status=STEP_PREPARED,
            )

        receipt = send_transaction(
            self.w3,
            self.account,
            function_call,
            gas_limit=gas_limit_for(name),
        )

        return CycleStep(
            name=name,
            detail=detail,
            status=STEP_SENT,
            tx_hash=receipt.tx_hash,
        )

    def _simulate_close(
        self,
        position: Position,
        wallet_balances: TokenBalances,
    ) -> ClosePositionResult:
        """Dry-run the decrease+collect multicall and decode the amounts."""
        results = self.position_manager.simulate_decrease_and_collect(
            position.token_id,
            position.liquidity,
        )

        return decode_decrease_and_collect_results(
            results,
            token0_balance_raw=wallet_balances.token0_raw,
            token1_balance_raw=wallet_balances.token1_raw,
        )

    def _plan_swap(
        self,
        *,
        state: PoolState,
        lower_tick: int,
        upper_tick: int,
        token0_balance_raw: int,
        token1_balance_raw: int,
    ) -> SwapPlan | None:
        """Return the swap that brings the balances to the range ratio."""
        return plan_swap_to_match_ratio(
            token0=state.token0,
            token1=state.token1,
            sqrt_price_x96=state.sqrt_price_x96,
            lower_tick=lower_tick,
            upper_tick=upper_tick,
            token0_balance_raw=token0_balance_raw,
            token1_balance_raw=token1_balance_raw,
            slippage_bps=self.config.slippage_bps,
            quote=self._quote_callable(state.fee),
        )

    def _quote_callable(
        self,
        fee: int,
    ) -> Callable[[str, str, int], int] | None:
        """Return the QuoterV2 lookup the planner should price a swap with.

        Without ``quoter.address`` the planner falls back to the spot price of
        the pool, which is only good enough for a DRY_RUN estimate.
        """
        if not self.can_quote:
            return None

        def quote(token_in: str, token_out: str, amount_in_raw: int) -> int:
            return self.swap_router.quote_exact_input_single(
                token_in,
                token_out,
                fee,
                amount_in_raw,
            )

        return quote

    def _read_new_token_id(self, known_token_ids: set[int]) -> int | None:
        """Return the token id minted by this cycle, if it can be told apart."""
        new_ids = sorted(
            set(self.position_manager.get_token_ids()) - known_token_ids
        )

        if len(new_ids) != 1:
            return None

        return new_ids[0]

    def _apply_gas_budget(
        self,
        state: PoolState,
        plan: RebalancePlan,
    ) -> tuple[RebalancePlan, str | None]:
        """Attach the estimated cycle cost and the configured gas ceiling."""
        max_cost_usd = self.config.max_gas_cost_usd

        if max_cost_usd is None:
            return plan, None

        operations = ["close_position", "mint"]

        if plan.swap_required:
            operations.append("swap")

        if self.config.burn_closed_position:
            operations.append("burn")

        if self.live:
            # One allowance for the mint plus one for the swap router.
            operations.append("approve")
            if plan.swap_required:
                operations.append("approve")

        cost_usd, gas_reason = self._gas_estimate(state, operations)

        plan = replace(
            plan,
            estimated_gas_cost_usd=cost_usd,
            max_gas_cost_usd=float(max_cost_usd),
        )
        plan.validate()

        return plan, gas_reason

    def _gas_estimate(
        self,
        state: PoolState,
        operations: list[str],
    ) -> tuple[float | None, str | None]:
        """Return the total estimated gas cost in USD and a block reason.

        The cost is priced with the oracle price of the wrapped native token
        when the pool holds it, otherwise the price of the native side of the
        pool is used. See ``blockchain.gas.resolve_native_token_price_usd``.
        """
        max_cost_usd = self.config.max_gas_cost_usd

        if max_cost_usd is None:
            return None, None

        native_price_usd = resolve_native_token_price_usd(
            state.token0,
            state.token1,
            self.config.weth_address,
            self.token0_price_usd,
            self.token1_price_usd,
        )

        gas_price_wei = int(self.w3.eth.gas_price)
        total_cost_usd = Decimal(0)

        for operation in operations:
            budget = check_gas_budget(
                gas_limit_for(operation),
                gas_price_wei,
                max_cost_usd,
                native_price_usd,
            )

            if not budget.allowed:
                return None, budget.reason

            total_cost_usd += budget.cost_usd

        return float(total_cost_usd), None

    def _record(
        self,
        result: CycleResult,
        *,
        state: PoolState,
        position: Position,
        decision: StrategyDecision,
        fees_value_usd: Decimal,
    ) -> None:
        """Store the cycle snapshot in the local store, when one is wired."""
        if self.store is None:
            return

        plan = result.plan
        swap = result.swap

        snapshot: dict[str, Any] = {
            "network": self.config.network,
            "pool_address": self.config.pool_address,
            "token_id": position.token_id,
            "current_tick": state.tick,
            "lower_tick": position.lower_tick,
            "upper_tick": position.upper_tick,
            "liquidity": str(position.liquidity),
            "fees_value_usd": str(fees_value_usd),
            "decision": decision.action,
            "in_range": decision.in_range,
            "proposed_lower_tick": decision.proposed_lower_tick,
            "proposed_upper_tick": decision.proposed_upper_tick,
            "mode": result.mode,
            "steps": [step.name for step in result.steps],
            "sent_steps": [step.name for step in result.sent_steps],
            "blocked_reason": result.blocked_reason,
            "new_token_id": result.new_token_id,
            "planned_liquidity": (
                None if plan is None else plan.planned_liquidity
            ),
            "swap_token_in": None if swap is None else swap.token_in,
            "swap_token_out": None if swap is None else swap.token_out,
            "swap_amount_in_raw": (
                None if swap is None else swap.amount_in_raw
            ),
            "min_amount_out_raw": (
                None if swap is None else swap.min_amount_out_raw
            ),
            "estimated_gas_cost_usd": (
                None if plan is None else plan.estimated_gas_cost_usd
            ),
        }

        self.store.record_event("rebalance_cycle", snapshot)
        self.store.record_decision(decision.action, snapshot)

