"""Wrap native ETH into WETH for the configured wallet.

Sends a transaction. Requires ``PRIVATE_KEY`` in ``.env`` and pays gas from
the wallet's native balance::

    python scripts/wrap_weth.py --amount-eth 0.0001
"""

import argparse
import sys
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ""):  # allow `python scripts/wrap_weth.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web3 import Web3

from blockchain.abis import WETH_ABI
from blockchain.rpc import connect
from config import AppConfig, load_config
from scripts._common import check_wallet, private_key


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--amount-eth",
        type=Decimal,
        default=Decimal("0.0001"),
        help="amount of native ETH to wrap (default: 0.0001)",
    )
    return parser.parse_args(argv)


def wrap_weth(config: AppConfig, amount_eth: Decimal) -> None:
    """Wrap ``amount_eth`` native ETH into WETH."""
    if amount_eth <= 0:
        raise ValueError("amount_eth must be positive")

    w3 = connect(config.rpc_url, expected_chain_id=config.expected_chain_id)
    account = w3.eth.account.from_key(private_key())
    check_wallet(config.wallet_address, account.address)

    weth = w3.eth.contract(
        address=Web3.to_checksum_address(config.weth_address),
        abi=WETH_ABI,
    )

    amount = w3.to_wei(amount_eth, "ether")

    tx = weth.functions.deposit().build_transaction(
        {
            "from": account.address,
            "value": amount,
            "nonce": w3.eth.get_transaction_count(account.address),
            "chainId": w3.eth.chain_id,
            "gas": 100_000,
            "gasPrice": w3.eth.gas_price,
        }
    )

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

    print(f"Wallet:      {account.address}")
    print(f"WETH:        {weth.address}")
    print(f"Amount:      {amount} wei")
    print(f"Transaction: {tx_hash.hex()}")
    print("Waiting for confirmation...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    print(f"Status:      {receipt.status}")
    print(f"Block:       {receipt.blockNumber}")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    wrap_weth(load_config(), args.amount_eth)


if __name__ == "__main__":
    main()
