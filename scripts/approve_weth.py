"""Approve unlimited WETH spending for the V3 position manager.

Sends a transaction. By default the allowance is unlimited, so a single run is
enough for repeated mints; ``--amount`` can still set an exact raw amount::

    python scripts/approve_weth.py
    python scripts/approve_weth.py --amount 200000000000000
"""

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python scripts/approve_weth.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web3 import Web3

from blockchain.abis import ERC20_ABI
from blockchain.erc20 import MAX_UINT256
from blockchain.rpc import connect
from config import AppConfig, load_config
from scripts._common import check_wallet, private_key


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--amount",
        type=int,
        default=MAX_UINT256,
        help="allowance in raw WETH units (default: unlimited)",
    )
    return parser.parse_args(argv)


def approve_weth(config: AppConfig, amount: int) -> None:
    """Approve ``amount`` raw WETH units for the position manager."""
    if amount <= 0:
        raise ValueError("amount must be positive")

    w3 = connect(config.rpc_url, expected_chain_id=config.expected_chain_id)
    account = w3.eth.account.from_key(private_key())
    check_wallet(config.wallet_address, account.address)

    spender = Web3.to_checksum_address(config.position_manager_address)

    weth = w3.eth.contract(
        address=Web3.to_checksum_address(config.weth_address),
        abi=ERC20_ABI,
    )

    allowance = weth.functions.allowance(account.address, spender).call()

    new_allowance = "unlimited" if amount == MAX_UINT256 else amount

    print(f"Wallet:           {account.address}")
    print(f"WETH:             {weth.address}")
    print(f"Position manager: {spender}")
    print(f"Current allowance:{allowance}")
    print(f"New allowance:    {new_allowance}")
    print()

    tx = weth.functions.approve(spender, amount).build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "chainId": w3.eth.chain_id,
            "gas": 100_000,
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
    approve_weth(load_config(), args.amount)


if __name__ == "__main__":
    main()
