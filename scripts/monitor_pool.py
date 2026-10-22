"""Read-only V3 pool report.

Prints the pool state once per ``strategy.check_interval`` seconds. Never
builds or sends transactions::

    python scripts/monitor_pool.py
"""

import sys
import time
from pathlib import Path

if __package__ in (None, ""):  # allow `python scripts/monitor_pool.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web3 import Web3

from blockchain.abis import ERC20_ABI
from blockchain.dex_manager import DEXManager
from blockchain.interfaces import PoolAdapter
from blockchain.rpc import connect
from config import AppConfig, load_config
from pool_guard import read_pool_state
from scripts._common import dex_title


def print_pool_info(
    w3: Web3,
    pool: PoolAdapter,
    config: AppConfig,
    chain_id: int,
) -> None:
    """Print a single pool snapshot."""
    state = read_pool_state(pool, config)

    token0 = w3.eth.contract(address=state.token0, abi=ERC20_ABI)
    token1 = w3.eth.contract(address=state.token1, abi=ERC20_ABI)

    token0_symbol = token0.functions.symbol().call()
    token1_symbol = token1.functions.symbol().call()

    print()
    print("=" * 50)
    print(f"{dex_title(config.dex)} LP Monitor")
    print("=" * 50)
    print(f"Network:       {config.network}")
    print(f"Chain ID:      {chain_id}")
    print(f"Pool:          {state.address}")
    print()
    print(f"Token0:        {token0_symbol} ({state.token0})")
    print(f"Token1:        {token1_symbol} ({state.token1})")
    print()
    print(f"Decimals:      {state.token0_decimals} / {state.token1_decimals}")
    print(f"Fee:           {state.fee / 10_000:.2f}%")
    print(f"Tick spacing:  {state.tick_spacing}")
    print()
    print(f"sqrtPriceX96:  {state.sqrt_price_x96}")
    print(f"Current tick:  {state.tick}")
    print(f"Liquidity:     {state.liquidity}")
    print(
        f"Price:         1 {token1_symbol} = "
        f"{state.price:.6f} {token0_symbol}"
    )
    print()
    print("Status:        MONITORING")
    print("=" * 50)


def monitor() -> None:
    config = load_config()
    w3 = connect(config.rpc_url, expected_chain_id=config.expected_chain_id)
    chain_id = int(w3.eth.chain_id)

    pool = DEXManager.create_pool(
        dex_name=config.dex,
        w3=w3,
        pool_address=config.pool_address,
    )

    print("LP Monitor started")
    print(f"Connecting to {config.dex} on {config.network}...")

    while True:
        try:
            print_pool_info(w3, pool, config, chain_id)
        except Exception as exc:  # keep the loop alive on transient RPC errors
            print(f"Monitor error: {exc}")

        time.sleep(config.check_interval)


if __name__ == "__main__":
    monitor()
