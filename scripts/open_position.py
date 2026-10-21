"""Open the first LP position from a wallet funded with one or two tokens.

The script reads the pool and wallet balances, derives the range from
``strategy.range_half_width`` (unless explicit ticks are passed), swaps only the
excess side and mints the NFT. It uses the same slippage limits and transaction
safety checks as the rebalance cycle.

Examples::

    python scripts/open_position.py --dry-run
    python scripts/open_position.py --amount-usd 10
    python scripts/open_position.py --tick-lower -198300 --tick-upper -198100

In ``DRY_RUN`` no key and no transaction are needed. In ``LIVE`` the wallet must
hold native ETH for gas; only pool tokens are invested. Native ETH is never
wrapped automatically: run ``scripts/wrap_weth.py`` first when the pool needs
WETH.
"""

import argparse
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ""):  # allow `python scripts/open_position.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web3 import Web3

from blockchain.dex_manager import DEXManager
from blockchain.erc20 import ERC20Token
from blockchain.gas import (
    check_gas_budget,
    gas_limit_for,
    resolve_native_token_price_usd,
)
from blockchain.position_manager import PositionManager
from blockchain.rpc import connect
from blockchain.swap_router import SwapRouter
from blockchain.token_balances import TokenBalances
from blockchain.tx import send_transaction
from config import MODE_DRY_RUN, MODE_LIVE, AppConfig, load_config
from monitor_position import resolve_token_prices
from position_opener import (
    OpenPositionPlan,
    cap_balances_to_usd,
    plan_open_position,
    range_ticks_for_pool,
)
from scripts._common import check_wallet, dex_title, private_key


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--amount-usd",
        type=Decimal,
        default=None,
        help="cap the invested value in USD (default: all pool-token balances)",
    )
    parser.add_argument(
        "--range-half-width",
        type=Decimal,
        default=None,
        help=(
            "relative half-width around the current price "
            "(default: strategy.range_half_width)"
        ),
    )
    parser.add_argument(
        "--tick-lower",
        type=int,
        default=None,
        help="explicit lower tick; requires --tick-upper",
    )
    parser.add_argument(
        "--tick-upper",
        type=int,
        default=None,
        help="explicit upper tick; requires --tick-lower",
    )
    parser.add_argument(
        "--slippage-bps",
        type=int,
        default=None,
        help="override strategy.slippage_bps (100 bps = 1%%)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="plan only, even when strategy.mode is LIVE",
    )
    return parser.parse_args(argv)


def _validate_args(args: argparse.Namespace) -> None:
    if args.amount_usd is not None and args.amount_usd <= 0:
        raise ValueError("--amount-usd must be positive")

    if args.range_half_width is not None and args.range_half_width <= 0:
        raise ValueError("--range-half-width must be positive")

    if (args.tick_lower is None) != (args.tick_upper is None):
        raise ValueError("--tick-lower and --tick-upper must be passed together")

    if args.tick_lower is not None and args.tick_lower >= args.tick_upper:
        raise ValueError("--tick-lower must be smaller than --tick-upper")

    if args.slippage_bps is not None and not 0 <= args.slippage_bps < 10_000:
        raise ValueError("--slippage-bps must be from 0 to 9999")


def _gas_preflight(
    w3: Web3,
    config: AppConfig,
    state,
    token0_price_usd: Decimal | None,
    token1_price_usd: Decimal | None,
    operations: list[str],
) -> tuple[float | None, str | None]:
    """Check the optional USD gas ceiling and, in LIVE, the native balance.

    ``DRY_RUN`` never signs anything, so a missing gas balance must not block
    the plan: the estimated cost is still reported when it can be priced.
    """
    gas_price_wei = int(w3.eth.gas_price)
    total_gas = sum(gas_limit_for(operation) for operation in operations)
    live = config.mode == MODE_LIVE

    if live:
        required_wei = total_gas * gas_price_wei + config.min_eth_balance_wei
        balance_wei = int(w3.eth.get_balance(config.wallet_address))

        if balance_wei < required_wei:
            return None, (
                f"Native balance {balance_wei} wei cannot cover the estimated "
                f"gas ({required_wei} wei including the configured reserve)"
            )

    max_cost_usd = config.max_gas_cost_usd

    if max_cost_usd is None:
        return None, None

    if token0_price_usd is None or token1_price_usd is None:
        if live:
            return None, (
                "Gas budget is configured but token prices are unavailable"
            )

        return None, None

    native_price_usd = resolve_native_token_price_usd(
        state.token0,
        state.token1,
        config.weth_address,
        token0_price_usd,
        token1_price_usd,
    )

    if native_price_usd is None:
        if live:
            return None, (
                "Gas budget is configured but the native token price is "
                "unknown"
            )

        return None, None

    total_cost_usd = Decimal(0)

    for operation in operations:
        budget = check_gas_budget(
            gas_limit_for(operation),
            gas_price_wei,
            max_cost_usd,
            native_price_usd,
        )

        if not budget.allowed and live:
            return None, budget.reason

        if budget.cost_usd is not None:
            total_cost_usd += budget.cost_usd

    return float(total_cost_usd), None


def _print_plan(
    config: AppConfig,
    state,
    plan: OpenPositionPlan,
    slippage_bps: int,
    gas_cost_usd: float | None,
) -> None:
    """Print the plan before any transaction is signed."""
    amount0_min, amount1_min = plan.mint_amount_limits(slippage_bps)

    print("=" * 60)
    print("OPEN LP POSITION")
    print("=" * 60)
    print(f"Mode:             {config.mode}")
    print(f"Network:          {config.network} ({config.expected_chain_id})")
    print(f"DEX:              {dex_title(config.dex)}")
    print(f"Pool:             {state.address}")
    print(f"Wallet:           {config.wallet_address}")
    print()
    print(f"Current tick:     {state.tick}")
    print(f"New range:        {plan.lower_tick} .. {plan.upper_tick}")
    print(f"Price (t0/t1):    {state.price}")
    print()
    print(f"Wallet token0:    {plan.token0_balance_raw} raw units")
    print(f"Wallet token1:    {plan.token1_balance_raw} raw units")

    if plan.swap is None:
        print("Swap:             not required")
    else:
        print(
            f"Swap:             {plan.swap.amount_in_raw} raw units "
            f"{plan.swap.token_in} -> {plan.swap.token_out}"
        )
        print(f"Quoted output:    {plan.swap.quoted_amount_out_raw}")
        print(
            f"Minimum output:   {plan.swap.min_amount_out_raw} "
            f"({slippage_bps} bps slippage)"
        )

    print()
    print(f"Available after swap: {plan.available_token0_after_swap_raw} / "
          f"{plan.available_token1_after_swap_raw} (token0/token1)")
    print(f"Required for LP:      {plan.required_token0_raw} / "
          f"{plan.required_token1_raw} (token0/token1)")
    print(f"Mint minimums:        {amount0_min} / {amount1_min} raw units")
    print(f"Planned liquidity:    {plan.planned_liquidity}")

    if gas_cost_usd is not None:
        print(f"Estimated gas:        ${gas_cost_usd:.6f}")

    if plan.blocked_reason:
        print(f"Blocked:              {plan.blocked_reason}")

    print("=" * 60)


def _send_or_prepare(
    w3: Web3,
    config: AppConfig,
    account,
    name: str,
    function_call,
    gas_limit: int,
    *,
    dry_run: bool,
) -> str | None:
    """Send a call in LIVE mode or print the prepared call in DRY_RUN."""
    if dry_run:
        print(f"[DRY_RUN] {name}: prepared, not sent")
        return None

    receipt = send_transaction(
        w3,
        account,
        function_call,
        gas_limit=gas_limit,
        min_balance_wei=config.min_eth_balance_wei,
        confirmations=config.tx_confirmations,
        timeout=config.tx_timeout_seconds,
    )
    print(f"{name}: {receipt.tx_hash} block={receipt.block_number}")
    return receipt.tx_hash


def _ensure_approval(
    w3: Web3,
    config: AppConfig,
    account,
    label: str,
    token: ERC20Token,
    spender: str,
    amount: int,
    *,
    dry_run: bool,
) -> None:
    """Grant an unlimited allowance when the current one is too small."""
    if not token.needs_approval(config.wallet_address, spender, amount):
        print(f"{label}: allowance already sufficient")
        return

    print(f"{label}: unlimited allowance for {spender}")
    _send_or_prepare(
        w3,
        config,
        account,
        f"approve {label}",
        token.build_max_approve(spender),
        gas_limit_for("approve"),
        dry_run=dry_run,
    )


def open_position(config: AppConfig, args: argparse.Namespace) -> int:
    """Plan and, in LIVE mode, execute the first position."""
    _validate_args(args)

    if args.dry_run:
        config = replace(config, mode=MODE_DRY_RUN)

    dry_run = config.mode != MODE_LIVE
    slippage_bps = (
        config.slippage_bps
        if args.slippage_bps is None
        else args.slippage_bps
    )

    w3 = connect(config.rpc_url, expected_chain_id=config.expected_chain_id)

    account = None
    if not dry_run:
        account = w3.eth.account.from_key(private_key())
        check_wallet(config.wallet_address, account.address)

    pool = DEXManager.create_pool(
        dex_name=config.dex,
        w3=w3,
        pool_address=config.pool_address,
    )
    state = pool.read_state()

    token0 = ERC20Token(w3, state.token0)
    token1 = ERC20Token(w3, state.token1)

    balances = TokenBalances(
        token0_raw=token0.balance_of(config.wallet_address),
        token1_raw=token1.balance_of(config.wallet_address),
    )

    token0_price_usd = None
    token1_price_usd = None

    if args.amount_usd is not None or config.max_gas_cost_usd is not None:
        token0_price_usd, token1_price_usd = resolve_token_prices(w3, config)

    if args.amount_usd is not None:
        if token0_price_usd is None or token1_price_usd is None:
            raise RuntimeError("Token prices are required for --amount-usd")

        balances = cap_balances_to_usd(
            balances,
            token0_decimals=state.token0_decimals,
            token1_decimals=state.token1_decimals,
            token0_price_usd=token0_price_usd,
            token1_price_usd=token1_price_usd,
            amount_usd=args.amount_usd,
        )

    if balances.token0_raw == 0 and balances.token1_raw == 0:
        print(
            "No pool tokens in the wallet: fund it with token0 and/or token1 "
            "first; native ETH is reserved for gas"
        )
        return 1

    if args.tick_lower is None:
        half_width = (
            config.range_half_width
            if args.range_half_width is None
            else args.range_half_width
        )
        lower_tick, upper_tick = range_ticks_for_pool(state, half_width)
    else:
        lower_tick = args.tick_lower
        upper_tick = args.tick_upper

        if lower_tick % state.tick_spacing or upper_tick % state.tick_spacing:
            raise ValueError(
                "ticks must be multiples of the pool tick spacing "
                f"({state.tick_spacing})"
            )

    swap_router = None
    quote = None

    if config.swap_router_address:
        swap_router = SwapRouter(
            w3,
            config.swap_router_address,
            config.quoter_address,
            config.dex,
        )

        if swap_router.can_quote:
            def quote(token_in: str, token_out: str, amount_in_raw: int) -> int:
                return swap_router.quote_exact_input_single(
                    token_in,
                    token_out,
                    state.fee,
                    amount_in_raw,
                )

    plan = plan_open_position(
        network=config.network,
        pool_address=config.pool_address,
        current_tick=state.tick,
        lower_tick=lower_tick,
        upper_tick=upper_tick,
        sqrt_price_x96=state.sqrt_price_x96,
        token0=state.token0,
        token1=state.token1,
        token0_balance_raw=balances.token0_raw,
        token1_balance_raw=balances.token1_raw,
        slippage_bps=slippage_bps,
        quote=quote,
    )

    if not dry_run and plan.swap_required and quote is None:
        raise RuntimeError(
            "LIVE mode needs swap_router.address and quoter.address to swap "
            "the excess token; configure the DEX profile first"
        )

    operations = []

    if plan.swap_required:
        operations.extend(("approve", "swap"))

    operations.extend(("approve", "approve", "mint"))

    gas_cost_usd, gas_reason = _gas_preflight(
        w3,
        config,
        state,
        token0_price_usd,
        token1_price_usd,
        operations,
    )

    _print_plan(config, state, plan, slippage_bps, gas_cost_usd)

    if plan.is_blocked:
        print(f"Refusing to open a position: {plan.blocked_reason}")
        return 1

    if gas_reason is not None:
        print(f"Refusing to open a position: {gas_reason}")
        return 1

    if plan.swap_required and swap_router is None:
        print(
            "Refusing to open a position: the balances need a swap, but no "
            "swap_router.address is configured for this DEX"
        )
        return 1

    position_manager = PositionManager(
        w3=w3,
        address=config.position_manager_address,
        wallet=config.wallet_address,
    )

    known_token_ids = set()
    if not dry_run:
        known_token_ids = set(position_manager.get_token_ids())

    if plan.swap is not None:
        token_in = (
            token0 if plan.swap.token_in_index == 0 else token1
        )

        _ensure_approval(
            w3,
            config,
            account,
            "token in (swap)",
            token_in,
            config.swap_router_address,
            plan.swap.amount_in_raw,
            dry_run=dry_run,
        )

        swap_call = swap_router.build_exact_input_single(
            token_in=plan.swap.token_in,
            token_out=plan.swap.token_out,
            fee=state.fee,
            recipient=config.wallet_address,
            amount_in_raw=plan.swap.amount_in_raw,
            min_amount_out_raw=plan.swap.min_amount_out_raw,
        )

        _send_or_prepare(
            w3,
            config,
            account,
            "swap",
            swap_call,
            gas_limit_for("swap"),
            dry_run=dry_run,
        )

    _ensure_approval(
        w3,
        config,
        account,
        "token0 (position manager)",
        token0,
        config.position_manager_address,
        plan.required_token0_raw,
        dry_run=dry_run,
    )
    _ensure_approval(
        w3,
        config,
        account,
        "token1 (position manager)",
        token1,
        config.position_manager_address,
        plan.required_token1_raw,
        dry_run=dry_run,
    )

    amount0_min, amount1_min = plan.mint_amount_limits(slippage_bps)

    mint_call = position_manager.build_mint(
        token0=state.token0,
        token1=state.token1,
        fee=state.fee,
        tick_lower=plan.lower_tick,
        tick_upper=plan.upper_tick,
        amount0_desired=plan.required_token0_raw,
        amount1_desired=plan.required_token1_raw,
        amount0_min=amount0_min,
        amount1_min=amount1_min,
        recipient=config.wallet_address,
    )

    _send_or_prepare(
        w3,
        config,
        account,
        "mint",
        mint_call,
        gas_limit_for("mint"),
        dry_run=dry_run,
    )

    if dry_run:
        print("DRY_RUN complete: no transaction was sent.")
        return 0

    new_ids = sorted(
        set(position_manager.get_token_ids()) - known_token_ids
    )

    if len(new_ids) == 1:
        print(f"New LP NFT: #{new_ids[0]}")
        print(
            f"Set dexes.{config.dex}.position_manager.token_id in "
            "config.yaml only when the wallet holds more than one matching "
            "position."
        )
    else:
        print(
            "Mint confirmed, but the new token id could not be determined "
            f"uniquely (new ids: {new_ids}). Run scripts/list_positions.py."
        )

    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        return open_position(load_config(), args)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

