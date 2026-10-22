"""Run one LP rebalancing cycle: plan it, then simulate it or send it.

``strategy.mode`` in ``config.yaml`` decides what the cycle does:

* ``DRY_RUN`` (default) verifies the steps whose preconditions are already on
  chain (``eth_call``) and prepares the rest, without signing anything;
* ``LIVE`` signs and broadcasts every step with ``PRIVATE_KEY`` from ``.env``,
  which also requires ``swap_router.address`` and ``quoter.address`` as soon as
  the cycle needs a swap::

    python scripts/rebalance.py

The cycle itself (``rebalance_cycle.RebalanceCycle``) never reads configuration
or the environment: everything is injected here.
"""

import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python scripts/rebalance.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web3 import Web3

from blockchain.dex_manager import DEXManager
from blockchain.interfaces import PoolAdapter
from blockchain.position_manager import PositionManager
from blockchain.rpc import connect
from blockchain.swap_router import SwapRouter
from config import MODE_LIVE, AppConfig, load_config
from monitor_position import resolve_native_price_usd, resolve_token_prices
from pool_guard import read_pool_state
from rebalance_cycle import CycleResult, RebalanceCycle, format_cycle_result
from scripts._common import check_wallet, private_key
from storage.sqlite_store import SQLiteStore
from strategy import Strategy


def build_swap_router(
    w3: Web3,
    config: AppConfig,
) -> SwapRouter | None:
    """Return the swap router, or ``None`` when no address is configured.

    Without ``swap_router.address`` the cycle cannot swap: it then only uses
    the local spot estimate to plan, and refuses to send a swap in ``LIVE``
    mode instead of executing one with an unsafe minimum output.
    """
    if not config.swap_router_address:
        return None

    return SwapRouter(
        w3=w3,
        address=config.swap_router_address,
        quoter_address=config.quoter_address,
        dex=config.dex,
    )


def build_cycle(
    w3: Web3,
    config: AppConfig,
    *,
    account: object | None = None,
    store: object | None = None,
) -> RebalanceCycle:
    """Wire one cycle from the configuration and the connected client."""
    pool: PoolAdapter = DEXManager.create_pool(
        dex_name=config.dex,
        w3=w3,
        pool_address=config.pool_address,
    )

    position_manager = PositionManager(
        w3=w3,
        address=config.position_manager_address,
        wallet=config.wallet_address,
    )

    strategy = Strategy(
        range_half_width=config.range_half_width,
        fee_threshold_usd=config.fee_threshold_usd,
    )

    # Token addresses come from the pool itself, so the oracle lookup follows
    # whatever pair the configured pool holds. The read also verifies the
    # optional pool.expected_* guards before any price is resolved.
    state = read_pool_state(pool, config)
    token0_price_usd, token1_price_usd = resolve_token_prices(
        w3,
        config,
        state.token0,
        state.token1,
    )
    native_price_usd = resolve_native_price_usd(w3, config)

    return RebalanceCycle(
        w3=w3,
        config=config,
        pool=pool,
        position_manager=position_manager,
        strategy=strategy,
        token0_price_usd=token0_price_usd,
        token1_price_usd=token1_price_usd,
        native_price_usd=native_price_usd,
        swap_router=build_swap_router(w3, config),
        account=account,
        store=store,
    )


def build_account(w3: Web3, config: AppConfig) -> object | None:
    """Return the signer for LIVE mode, or ``None`` for a dry run.

    The configured wallet and ``PRIVATE_KEY`` are compared once at startup so
    that a daemon cannot run for hours against the wrong account.
    """
    if config.mode != MODE_LIVE:
        return None

    account = w3.eth.account.from_key(private_key())
    check_wallet(config.wallet_address, account.address)
    return account


def run_cycle(
    w3: Web3,
    config: AppConfig,
    *,
    account: object | None = None,
    store: object | None = None,
) -> CycleResult:
    """Build and execute one cycle, returning its structured result."""
    return build_cycle(
        w3,
        config,
        account=account,
        store=store,
    ).run()


def main() -> None:
    config = load_config()
    w3 = connect(config.rpc_url, expected_chain_id=config.expected_chain_id)

    account = build_account(w3, config)
    result = run_cycle(
        w3,
        config,
        account=account,
        store=SQLiteStore(),
    )

    print(format_cycle_result(result))


if __name__ == "__main__":
    main()
