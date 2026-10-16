"""Mint a new PancakeSwap V3 LP position.

Sends a transaction and is intended for manual experiments: it mints the
requested tick range with the requested amounts and no slippage protection
(``amount0Min``/``amount1Min`` are 0), which is safe only for amounts you are
willing to lose::

    python scripts/mint_position.py --tick-lower 219000 --tick-upper 219200
"""

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python scripts/mint_position.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web3 import Web3

from blockchain.abis import POSITION_MANAGER_ABI
from blockchain.dex_manager import DEXManager
from blockchain.rpc import connect
from config import AppConfig, load_config
from scripts._common import private_key

DEADLINE_SECONDS = 600


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--amount0",
        type=int,
        default=1_000_000,
        help="amount of token0 in raw units (default: 1000000)",
    )
    parser.add_argument(
        "--amount1",
        type=int,
        default=100_000_000_000_000,
        help="amount of token1 in raw units (default: 100000000000000)",
    )
    parser.add_argument(
        "--tick-lower",
        type=int,
        default=219_000,
        help="lower tick, must be a multiple of the pool tick spacing",
    )
    parser.add_argument(
        "--tick-upper",
        type=int,
        default=219_200,
        help="upper tick, must be a multiple of the pool tick spacing",
    )
    return parser.parse_args(argv)


def mint_position(
    config: AppConfig,
    amount0_desired: int,
    amount1_desired: int,
    tick_lower: int,
    tick_upper: int,
) -> None:
    """Mint a position in the configured pool."""
    if amount0_desired <= 0 or amount1_desired <= 0:
        raise ValueError("amounts must be positive")

    if tick_lower >= tick_upper:
        raise ValueError("tick_lower must be smaller than tick_upper")

    w3 = connect(config.rpc_url, expected_chain_id=config.expected_chain_id)
    account = w3.eth.account.from_key(private_key())

    pool = DEXManager.create_pool(
        dex_name=config.dex,
        w3=w3,
        pool_address=config.pool_address,
    )
    state = pool.read_state()

    if tick_lower % state.tick_spacing or tick_upper % state.tick_spacing:
        raise ValueError(
            f"ticks must be multiples of the pool tick spacing "
            f"({state.tick_spacing})"
        )

    position_manager = w3.eth.contract(
        address=Web3.to_checksum_address(config.position_manager_address),
        abi=POSITION_MANAGER_ABI,
    )

    params = (
        state.token0,
        state.token1,
        state.fee,
        tick_lower,
        tick_upper,
        amount0_desired,
        amount1_desired,
        0,
        0,
        account.address,
        w3.eth.get_block("latest")["timestamp"] + DEADLINE_SECONDS,
    )

    print("=" * 50)
    print("LP MINT")
    print("=" * 50)
    print(f"Wallet:        {account.address}")
    print(f"Pool:          {state.address}")
    print(f"Token0:        {state.token0}")
    print(f"Token1:        {state.token1}")
    print(f"Fee:           {state.fee}")
    print(f"Current tick:  {state.tick}")
    print(f"Tick lower:    {tick_lower}")
    print(f"Tick upper:    {tick_upper}")
    print(f"Amount0:       {amount0_desired}")
    print(f"Amount1:       {amount1_desired}")
    print("=" * 50)

    tx = position_manager.functions.mint(params).build_transaction(
        {
            "from": account.address,
            "value": 0,
            "nonce": w3.eth.get_transaction_count(account.address),
            "chainId": w3.eth.chain_id,
            "gas": 500_000,
            "gasPrice": w3.eth.gas_price,
        }
    )

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

    print(f"Transaction: {tx_hash.hex()}")
    print("Waiting for confirmation...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    print(f"Status:      {receipt.status}")
    print(f"Block:       {receipt.blockNumber}")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    mint_position(
        load_config(),
        args.amount0,
        args.amount1,
        args.tick_lower,
        args.tick_upper,
    )


if __name__ == "__main__":
    main()
