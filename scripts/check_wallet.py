"""Verify that ``PRIVATE_KEY`` in ``.env`` controls ``wallet.address``.

Read-only: no RPC connection and no transactions are made. Run this after
copying ``.env.example`` to ``.env`` and adding the key::

    python scripts/check_wallet.py
"""

import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python scripts/check_wallet.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web3 import Web3

from config import load_config
from scripts._common import check_wallet, private_key


def main() -> int:
    try:
        config = load_config()
        signer = Web3().eth.account.from_key(private_key())
        check_wallet(config.wallet_address, signer.address)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"OK: PRIVATE_KEY controls {signer.address}")
    print(f"Network: {config.network} (chain_id={config.expected_chain_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())