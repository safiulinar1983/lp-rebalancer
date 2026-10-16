"""Tests for the cycle executor: step order, step statuses and blocking.

Every fake here stands in for one collaborator (pool, position manager, swap
router, ERC20 token): the cycle under test only decides *what* to send, so the
sending helpers themselves are patched out.
"""

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from eth_abi import encode

import rebalance_cycle
from blockchain.liquidity_math import Q96
from blockchain.pancake_v3 import PoolState
from blockchain.positions import Position
from blockchain.tx import TxReceipt
from config import MODE_DRY_RUN, MODE_LIVE, load_config
from rebalance_cycle import (
    STEP_PREPARED,
    STEP_SENT,
    STEP_SIMULATED,
    CycleResult,
    CycleStep,
    RebalanceCycle,
    format_cycle_result,
)
from strategy import StrategyDecision

TOKEN0 = "0x0000000000000000000000000000000000000001"
TOKEN1 = "0x0000000000000000000000000000000000000002"
WALLET = "0x0000000000000000000000000000000000000003"
POSITION_MANAGER = "0x0000000000000000000000000000000000000004"
SWAP_ROUTER = "0x0000000000000000000000000000000000000005"
WETH = "0x4200000000000000000000000000000000000006"

TOKEN_ID = 82740
SQRT_PRICE_X96 = int(Q96)
GAS_PRICE_WEI = 1_000_000_000


class FakeFunctionCall:
    """Stand-in for a prepared contract call, carrying its own name."""

    def __init__(self, name, **params):
        self.name = name
        self.params = params
        self.simulations = []

    def call(self, transaction):
        """Record the ``eth_call`` the DRY_RUN path performs."""
        self.simulations.append(transaction)
        return None


class FakeToken:
    """Minimal ERC20: a fixed balance and an allowance that is never enough."""

    def __init__(self, balance):
        self.balance = balance
        self.approvals = []

    def balance_of(self, owner):
        self.owner = owner
        return self.balance

    def needs_approval(self, owner, spender, amount):
        return amount > 0

    def build_approve(self, spender, amount):
        self.approvals.append((spender, amount))
        return FakeFunctionCall("approve", spender=spender, amount=amount)


def make_state(**overrides):
    values = {
        "address": "0x0000000000000000000000000000000000000009",
        "token0": TOKEN0,
        "token1": TOKEN1,
        "token0_decimals": 6,
        "token1_decimals": 18,
        "fee": 500,
        "tick_spacing": 10,
        "sqrt_price_x96": SQRT_PRICE_X96,
        "tick": 0,
        "liquidity": 1_000_000,
        "price": Decimal("1"),
    }
    values.update(overrides)
    return PoolState(**values)


def make_position(**overrides):
    values = {
        "token_id": TOKEN_ID,
        "token0": TOKEN0,
        "token1": TOKEN1,
        "fee": 500,
        "lower_tick": 219_000,
        "upper_tick": 219_100,
        "liquidity": 1_000_000,
        "tokens_owed0": 0,
        "tokens_owed1": 0,
    }
    values.update(overrides)
    return Position(**values)


def make_decision(action, state, position, proposed=None):
    return StrategyDecision(
        current_tick=state.tick,
        lower_tick=position.lower_tick,
        upper_tick=position.upper_tick,
        in_range=action != "REBALANCE",
        action=action,
        proposed_lower_tick=None if proposed is None else proposed[0],
        proposed_upper_tick=None if proposed is None else proposed[1],
    )


def close_multicall_results(close_amounts):
    """Return the two multicall results a dry-run close would produce."""
    return [
        encode(["uint256", "uint256"], [0, 0]),
        encode(["uint256", "uint256"], list(close_amounts)),
    ]


def make_cycle(
    *,
    config=None,
    state=None,
    position=None,
    action="HOLD",
    proposed=None,
    fees=(0, 0),
    close_amounts=(0, 0),
    wallet_balances=(10_000_000_000, 0),
    token_ids=(TOKEN_ID,),
    minted_token_id=None,
    prices=(Decimal("1"), Decimal("2500")),
    swap_router=None,
    account=None,
    store=None,
):
    """Return ``(cycle, position_manager, tokens)`` with every call faked."""
    config = load_config() if config is None else config
    state = make_state() if state is None else state
    position = (
        make_position(
            token0=state.token0,
            token1=state.token1,
            fee=state.fee,
        )
        if position is None
        else position
    )

    token_id_reads = [list(token_ids)]
    token_id_reads.append(
        list(token_ids)
        if minted_token_id is None
        else [*token_ids, minted_token_id]
    )

    position_manager = SimpleNamespace(
        address=POSITION_MANAGER,
        find_position=Mock(return_value=position),
        simulate_collect_fees=Mock(return_value=fees),
        simulate_decrease_and_collect=Mock(
            return_value=close_multicall_results(close_amounts)
        ),
        build_collect=Mock(return_value=FakeFunctionCall("collect")),
        build_burn=Mock(return_value=FakeFunctionCall("burn")),
        build_close_position=Mock(
            return_value=FakeFunctionCall("close_position")
        ),
        build_increase_liquidity=Mock(
            return_value=FakeFunctionCall("increase_liquidity")
        ),
        build_mint=Mock(return_value=FakeFunctionCall("mint")),
        get_token_ids=Mock(side_effect=token_id_reads),
    )

    strategy = SimpleNamespace(
        evaluate=Mock(
            return_value=make_decision(action, state, position, proposed)
        )
    )

    tokens = {
        state.token0: FakeToken(wallet_balances[0]),
        state.token1: FakeToken(wallet_balances[1]),
    }

    cycle = RebalanceCycle(
        w3=SimpleNamespace(
            eth=SimpleNamespace(gas_price=GAS_PRICE_WEI),
        ),
        config=config,
        pool=SimpleNamespace(read_state=Mock(return_value=state)),
        position_manager=position_manager,
        strategy=strategy,
        token0_price_usd=prices[0],
        token1_price_usd=prices[1],
        swap_router=swap_router,
        account=account,
        store=store,
        token_factory=lambda address: tokens[address],
    )

    return cycle, position_manager, tokens


def test_hold_sends_nothing():
    cycle, position_manager, _ = make_cycle(action="HOLD")

    result = cycle.run()

    assert result.mode == MODE_DRY_RUN
    assert result.action == "HOLD"
    assert result.steps == ()
    assert result.plan is None
    assert result.swap is None
    assert result.blocked is False
    assert result.blocked_reason is None
    assert result.new_token_id is None
    assert result.sent_steps == ()
    position_manager.build_collect.assert_not_called()
    position_manager.build_mint.assert_not_called()


def test_run_reads_the_position_and_its_fees_before_deciding():
    cycle, position_manager, _ = make_cycle(action="HOLD")

    cycle.run()

    position_manager.find_position.assert_called_once_with(
        token0=TOKEN0,
        token1=TOKEN1,
        fee=500,
        token_id=TOKEN_ID,
    )
    position_manager.simulate_collect_fees.assert_called_once_with(TOKEN_ID)


def test_collect_fees_compounds_into_the_same_nft():
    config = replace(load_config(), fee_threshold_usd=Decimal("0"))
    position = make_position(lower_tick=100, upper_tick=200)
    cycle, position_manager, _ = make_cycle(
        config=config,
        action="COLLECT_FEES",
        position=position,
        fees=(1000, 0),
    )

    result = cycle.run()

    assert result.action == "COLLECT_FEES"
    assert result.blocked is False
    assert result.plan is None
    assert result.swap is None
    assert [step.name for step in result.steps] == [
        "collect",
        "approve",
        "increase_liquidity",
    ]
    assert [step.status for step in result.steps] == [
        STEP_SIMULATED,
        STEP_SIMULATED,
        STEP_PREPARED,
    ]
    position_manager.simulate_collect_fees.assert_called_once_with(TOKEN_ID)
    position_manager.build_collect.assert_called_once_with(TOKEN_ID)
    position_manager.build_increase_liquidity.assert_called_once_with(
        TOKEN_ID,
        1000,
        0,
        995,
        0,
    )


def test_collect_fees_swaps_the_excess_token_before_compounding():
    config = replace(load_config(), fee_threshold_usd=Decimal("0"))
    position = make_position(lower_tick=100, upper_tick=200)
    cycle, position_manager, _ = make_cycle(
        config=config,
        action="COLLECT_FEES",
        position=position,
        fees=(0, 1000),
    )

    result = cycle.run()

    assert [step.name for step in result.steps] == [
        "collect",
        "swap",
        "approve",
        "increase_liquidity",
    ]
    assert [step.status for step in result.steps] == [
        STEP_SIMULATED,
        STEP_PREPARED,
        STEP_SIMULATED,
        STEP_PREPARED,
    ]
    assert result.swap.token_in == TOKEN1
    assert result.swap.token_out == TOKEN0
    assert result.swap.amount_in_raw == 1000
    assert result.swap.quoted_amount_out_raw == 1000
    assert result.swap.min_amount_out_raw == 995
    assert TOKEN1 in result.steps[1].detail
    assert result.steps[1].detail.endswith(
        "(prepared from the local spot estimate)"
    )
    position_manager.build_increase_liquidity.assert_called_once_with(
        TOKEN_ID,
        1000,
        0,
        995,
        0,
    )


def test_collect_fees_are_blocked_when_there_is_nothing_to_compound():
    config = replace(load_config(), fee_threshold_usd=Decimal("0"))
    cycle, _, _ = make_cycle(
        config=config,
        action="COLLECT_FEES",
        fees=(0, 0),
    )

    result = cycle.run()

    assert result.blocked is True
    assert "too small" in result.blocked_reason
    assert [step.name for step in result.steps] == ["collect"]
    assert "too small" in format_cycle_result(result)


def make_sender():
    """Return a ``send_transaction`` stand-in and the list of calls it got.

    ``rebalance_cycle`` imports the helper by name, so tests replace it on the
    module instead of reaching into the network layer.
    """
    sent = []

    def sender(w3, account, function_call, *, gas_limit):
        sent.append((function_call.name, gas_limit))
        return TxReceipt(
            tx_hash=f"0x{len(sent):064x}",
            status=1,
            block_number=len(sent),
            gas_used=gas_limit // 2,
        )

    return sender, sent


def test_rebalance_dry_run_closes_swaps_and_mints():
    cycle, position_manager, _ = make_cycle(
        action="REBALANCE",
        proposed=(-100, 100),
        close_amounts=(5_000_000_000, 0),
        wallet_balances=(5_000_000_000, 0),
    )

    result = cycle.run()

    assert result.action == "REBALANCE"
    assert result.mode == MODE_DRY_RUN
    assert result.blocked is False
    assert result.sent_steps == ()
    assert result.new_token_id is None
    assert [step.name for step in result.steps] == [
        "close_position",
        "swap",
        "approve",
        "approve",
        "mint",
    ]
    assert [step.status for step in result.steps] == [
        STEP_SIMULATED,
        STEP_PREPARED,
        STEP_SIMULATED,
        STEP_SIMULATED,
        STEP_PREPARED,
    ]

    assert result.plan.swap_required is True
    assert result.plan.planned_liquidity > 0
    assert result.swap.token_in == TOKEN0
    assert result.swap.token_out == TOKEN1
    assert result.swap.amount_in_raw == 5_000_000_000
    assert result.swap.min_amount_out_raw == 4_975_000_000
    assert result.steps[1].detail.endswith(
        "(prepared from the local spot estimate)"
    )

    # The close is verified through eth_call; 10e9 raw units of token0 are
    # left in the wallet, so half of them has to be sold before the mint.
    position_manager.build_close_position.assert_called_once_with(
        TOKEN_ID,
        1_000_000,
    )
    assert position_manager.build_close_position.return_value.simulations == [
        {"from": cycle.config.wallet_address}
    ]


def test_rebalance_dry_run_burns_the_emptied_nft():
    config = replace(load_config(), burn_closed_position=True)
    cycle, position_manager, _ = make_cycle(
        config=config,
        action="REBALANCE",
        proposed=(-100, 100),
        close_amounts=(5_000_000_000, 0),
    )

    result = cycle.run()

    assert [step.name for step in result.steps] == [
        "close_position",
        "burn",
        "swap",
        "approve",
        "approve",
        "mint",
    ]
    assert result.steps[1].status == STEP_SIMULATED
    position_manager.build_burn.assert_called_once_with(TOKEN_ID)


def test_rebalance_dry_run_without_a_swap_skips_the_swap_steps():
    cycle, position_manager, _ = make_cycle(
        action="REBALANCE",
        proposed=(-100, 100),
        close_amounts=(5_000_000_000, 5_000_000_000),
        wallet_balances=(0, 0),
    )

    result = cycle.run()

    assert result.swap is None
    assert result.plan.swap_required is False
    assert [step.name for step in result.steps] == [
        "close_position",
        "approve",
        "approve",
        "mint",
    ]
    position_manager.simulate_collect_fees.assert_called_once_with(TOKEN_ID)


def test_rebalance_live_sends_every_step_in_order(monkeypatch):
    sender, sent = make_sender()
    monkeypatch.setattr(rebalance_cycle, "send_transaction", sender)

    router = SimpleNamespace(
        address=SWAP_ROUTER,
        can_quote=True,
        quote_exact_input_single=Mock(return_value=4_900_000_000),
        build_exact_input_single=Mock(
            return_value=FakeFunctionCall("swap")
        ),
    )

    config = replace(load_config(), mode=MODE_LIVE)
    cycle, position_manager, tokens = make_cycle(
        config=config,
        action="REBALANCE",
        proposed=(-100, 100),
        close_amounts=(5_000_000_000, 0),
        wallet_balances=(5_000_000_000, 0),
        minted_token_id=111,
        swap_router=router,
        account=SimpleNamespace(),
    )

    result = cycle.run()

    assert result.mode == MODE_LIVE
    assert result.blocked is False
    assert result.new_token_id == 111
    assert result.sent_steps == result.steps
    assert all(step.tx_hash for step in result.steps)

    assert [name for name, _ in sent] == [
        "close_position",
        "approve",
        "swap",
        "approve",
        "approve",
        "mint",
    ]
    assert [limit for _, limit in sent] == [
        700_000,
        80_000,
        400_000,
        80_000,
        80_000,
        700_000,
    ]

    swap = result.swap
    assert swap.quoted_amount_out_raw == 4_900_000_000
    assert swap.min_amount_out_raw == 4_875_500_000
    router.quote_exact_input_single.assert_called_once_with(
        TOKEN0,
        TOKEN1,
        500,
        swap.amount_in_raw,
    )
    router.build_exact_input_single.assert_called_once_with(
        TOKEN0,
        TOKEN1,
        500,
        config.wallet_address,
        swap.amount_in_raw,
        4_875_500_000,
    )

    assert (SWAP_ROUTER, swap.amount_in_raw) in tokens[TOKEN0].approvals
    assert (
        POSITION_MANAGER,
        result.plan.required_token0_raw,
    ) in tokens[TOKEN0].approvals
    assert (
        POSITION_MANAGER,
        result.plan.required_token1_raw,
    ) in tokens[TOKEN1].approvals

    # The new NFT is found by comparing the wallet positions before and after.
    assert position_manager.get_token_ids.call_count == 2


def test_new_token_id_is_ignored_when_it_cannot_be_told_apart(monkeypatch):
    sender, _ = make_sender()
    monkeypatch.setattr(rebalance_cycle, "send_transaction", sender)

    router = SimpleNamespace(
        address=SWAP_ROUTER,
        can_quote=True,
        quote_exact_input_single=Mock(return_value=4_900_000_000),
        build_exact_input_single=Mock(
            return_value=FakeFunctionCall("swap")
        ),
    )

    config = replace(load_config(), mode=MODE_LIVE)
    cycle, position_manager, _ = make_cycle(
        config=config,
        action="REBALANCE",
        proposed=(-100, 100),
        close_amounts=(5_000_000_000, 0),
        wallet_balances=(5_000_000_000, 0),
        swap_router=router,
        account=SimpleNamespace(),
    )
    position_manager.get_token_ids = Mock(
        side_effect=[[TOKEN_ID], [TOKEN_ID, 111, 222]]
    )

    result = cycle.run()

    assert result.blocked is False
    assert result.new_token_id is None


def test_rebalance_live_without_a_quote_is_blocked(monkeypatch):
    sender, sent = make_sender()
    monkeypatch.setattr(rebalance_cycle, "send_transaction", sender)

    router = SimpleNamespace(
        address=SWAP_ROUTER,
        can_quote=False,
        quote_exact_input_single=Mock(),
        build_exact_input_single=Mock(),
    )

    config = replace(load_config(), mode=MODE_LIVE)
    cycle, position_manager, _ = make_cycle(
        config=config,
        action="REBALANCE",
        proposed=(-100, 100),
        close_amounts=(5_000_000_000, 0),
        swap_router=router,
        account=SimpleNamespace(),
    )

    result = cycle.run()

    assert result.blocked is True
    assert "quoter.address" in result.blocked_reason
    assert result.plan.is_blocked is True
    assert result.steps == ()
    assert sent == []
    router.build_exact_input_single.assert_not_called()
    position_manager.build_mint.assert_not_called()


def test_rebalance_live_without_a_configured_router_is_blocked(monkeypatch):
    sender, sent = make_sender()
    monkeypatch.setattr(rebalance_cycle, "send_transaction", sender)

    config = replace(load_config(), mode=MODE_LIVE)
    cycle, _, _ = make_cycle(
        config=config,
        action="REBALANCE",
        proposed=(-100, 100),
        close_amounts=(5_000_000_000, 0),
        account=SimpleNamespace(),
    )

    result = cycle.run()

    assert result.blocked is True
    assert "quoter.address" in result.blocked_reason
    assert sent == []


def test_live_mode_requires_an_unlocked_account():
    config = replace(load_config(), mode=MODE_LIVE)

    with pytest.raises(ValueError, match="PRIVATE_KEY"):
        make_cycle(config=config)


def test_gas_budget_without_a_native_price_blocks_the_cycle():
    # Neither pool token is the wrapped native token, so gas cannot be valued.
    config = replace(load_config(), max_gas_cost_usd=Decimal("1"))
    cycle, position_manager, _ = make_cycle(
        config=config,
        action="REBALANCE",
        proposed=(-100, 100),
        close_amounts=(5_000_000_000, 0),
    )

    result = cycle.run()

    assert result.blocked is True
    assert "native token price is unknown" in result.blocked_reason
    assert result.steps == ()
    position_manager.build_mint.assert_not_called()


def test_gas_budget_above_the_limit_blocks_the_cycle():
    config = replace(load_config(), max_gas_cost_usd=Decimal("0.01"))
    state = make_state(token0=WETH, token1=TOKEN1)
    cycle, _, _ = make_cycle(
        config=config,
        state=state,
        action="REBALANCE",
        proposed=(-100, 100),
        close_amounts=(5_000_000_000, 0),
        prices=(Decimal("2500"), Decimal("1")),
    )

    result = cycle.run()

    assert result.blocked is True
    assert "exceeds the configured limit" in result.blocked_reason
    assert result.steps == ()


def test_gas_estimate_is_attached_to_the_plan():
    # $2500 per native token, 1 gwei: close + swap + mint cost $4.5 together.
    config = replace(load_config(), max_gas_cost_usd=Decimal("10"))
    state = make_state(token0=WETH, token1=TOKEN1)
    cycle, _, _ = make_cycle(
        config=config,
        state=state,
        action="REBALANCE",
        proposed=(-100, 100),
        close_amounts=(5_000_000_000, 0),
        prices=(Decimal("2500"), Decimal("1")),
    )

    result = cycle.run()

    assert result.blocked is False
    assert result.swap is not None
    assert result.plan.estimated_gas_cost_usd == pytest.approx(4.5)
    assert result.plan.max_gas_cost_usd == 10.0
    assert "Gas estimate:  $4.500000" in format_cycle_result(result)


def test_approvals_are_skipped_when_the_allowance_is_enough():
    cycle, position_manager, tokens = make_cycle(
        action="REBALANCE",
        proposed=(-100, 100),
        close_amounts=(5_000_000_000, 0),
    )
    tokens[TOKEN0].needs_approval = Mock(return_value=False)
    tokens[TOKEN1].needs_approval = Mock(return_value=False)

    result = cycle.run()

    assert [step.name for step in result.steps] == [
        "close_position",
        "swap",
        "mint",
    ]
    position_manager.build_mint.assert_called_once()


def test_cycle_snapshot_is_stored_in_both_tables():
    store = SimpleNamespace(record_event=Mock(), record_decision=Mock())
    cycle, _, _ = make_cycle(
        action="REBALANCE",
        proposed=(-100, 100),
        close_amounts=(5_000_000_000, 0),
        wallet_balances=(5_000_000_000, 0),
        store=store,
    )

    result = cycle.run()

    event_type, snapshot = store.record_event.call_args.args
    assert event_type == "rebalance_cycle"
    assert snapshot["network"] == cycle.config.network
    assert snapshot["mode"] == MODE_DRY_RUN
    assert snapshot["decision"] == "REBALANCE"
    assert snapshot["in_range"] is False
    assert snapshot["proposed_lower_tick"] == -100
    assert snapshot["proposed_upper_tick"] == 100
    assert snapshot["steps"] == [step.name for step in result.steps]
    assert snapshot["sent_steps"] == []
    assert snapshot["blocked_reason"] is None
    assert snapshot["new_token_id"] is None
    assert snapshot["swap_token_in"] == TOKEN0
    assert snapshot["swap_token_out"] == TOKEN1
    assert snapshot["swap_amount_in_raw"] == 5_000_000_000
    assert snapshot["min_amount_out_raw"] == 4_975_000_000
    assert snapshot["planned_liquidity"] == result.plan.planned_liquidity
    assert snapshot["estimated_gas_cost_usd"] is None
    store.record_decision.assert_called_once_with("REBALANCE", snapshot)


def test_snapshot_of_a_collect_cycle_has_no_plan_numbers():
    store = SimpleNamespace(record_event=Mock(), record_decision=Mock())
    position = make_position(lower_tick=100, upper_tick=200)
    cycle, _, _ = make_cycle(
        action="COLLECT_FEES",
        position=position,
        fees=(1000, 0),
        store=store,
    )

    cycle.run()

    _, snapshot = store.record_event.call_args.args
    assert snapshot["decision"] == "COLLECT_FEES"
    assert snapshot["steps"] == [
        "collect",
        "approve",
        "increase_liquidity",
    ]
    assert snapshot["swap_amount_in_raw"] is None
    assert snapshot["planned_liquidity"] is None
    assert snapshot["estimated_gas_cost_usd"] is None


def test_no_snapshot_is_stored_without_a_store():
    cycle, _, _ = make_cycle(action="HOLD")

    assert cycle.store is None
    assert cycle.run().blocked is False


def test_report_lists_the_steps_and_the_swap():
    cycle, _, _ = make_cycle(
        action="REBALANCE",
        proposed=(-100, 100),
        close_amounts=(5_000_000_000, 0),
        wallet_balances=(5_000_000_000, 0),
    )

    report = format_cycle_result(cycle.run())

    assert "Mode:          DRY_RUN" in report
    assert "Action:        REBALANCE" in report
    assert "New range:     -100..100" in report
    assert f"Swap:          5000000000 raw units of {TOKEN0}" in report
    assert f"min 4975000000 raw units of {TOKEN1}" in report
    assert "1. close_position [simulated]" in report
    assert "2. swap [prepared]" in report
    assert "5. mint [prepared]" in report


def test_hold_report_says_no_steps_required():
    cycle, _, _ = make_cycle(action="HOLD")

    report = format_cycle_result(cycle.run())

    assert "No steps required." in report
    assert "Blocked:" not in report


def test_blocked_report_names_the_reason():
    cycle, _, _ = make_cycle(
        action="COLLECT_FEES",
        fees=(0, 0),
    )

    report = format_cycle_result(cycle.run())

    assert "Blocked:       Collected fees are too small" in report


def test_sent_step_requires_a_transaction_hash():
    with pytest.raises(ValueError, match="transaction hash"):
        CycleStep(name="swap", detail="d", status=STEP_SENT)

    with pytest.raises(ValueError, match="Only sent steps"):
        CycleStep(
            name="swap",
            detail="d",
            status=STEP_SIMULATED,
            tx_hash="0x1",
        )

    with pytest.raises(ValueError, match="Unknown step status"):
        CycleStep(name="swap", detail="d", status="pending")


def test_step_sent_flag_follows_the_status():
    sent = CycleStep(
        name="swap",
        detail="d",
        status=STEP_SENT,
        tx_hash="0xabc",
    )

    assert sent.sent is True
    assert sent.tx_hash == "0xabc"
    assert CycleStep(
        name="mint",
        detail="d",
        status=STEP_PREPARED,
    ).sent is False


def test_result_without_steps_is_not_blocked():
    result = CycleResult(mode=MODE_DRY_RUN, action="HOLD")

    assert result.blocked is False
    assert result.sent_steps == ()

