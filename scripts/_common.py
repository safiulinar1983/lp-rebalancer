"""Helpers shared by the manual CLI scripts.

Importing this module is side effect free: it only defines helpers.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def private_key() -> str:
    """Return ``PRIVATE_KEY`` from the environment, loading ``.env`` first."""
    load_dotenv(PROJECT_ROOT / ".env")

    key = os.environ.get("PRIVATE_KEY", "").strip()

    if not key:
        raise RuntimeError(
            "PRIVATE_KEY is not set: put it in .env (see .env.example)"
        )

    return key


def check_wallet(wallet_address: str, signer_address: str) -> None:
    """Fail when ``PRIVATE_KEY`` does not control the configured wallet.

    Balances and token ownership are read for ``wallet.address``, so a
    mismatch would silently prepare transactions for a different account.
    Addresses are compared case-insensitively.
    """
    if wallet_address.lower() == signer_address.lower():
        return

    raise RuntimeError(
        "PRIVATE_KEY does not match wallet.address: "
        f"signer {signer_address}, configured {wallet_address}"
    )


DEX_TITLES = {
    "uniswap_v3": "Uniswap V3",
    "pancakeswap_v3": "PancakeSwap V3",
}


def dex_title(dex: str) -> str:
    """Return a human-readable DEX name for CLI headers."""
    return DEX_TITLES.get(dex.lower(), dex)
