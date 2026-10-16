"""Validation of the parameters that end up in on-chain calls.

Both adapters (``blockchain.position_manager`` and ``blockchain.swap_router``)
build calldata from raw integers and addresses, so the checks live here instead
of being duplicated with a chance to drift apart.
"""

from web3 import Web3


def positive_amount(value: object, name: str) -> int:
    """Return a raw amount that must be strictly positive."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")

    return value


def non_negative_amount(value: object, name: str) -> int:
    """Return a raw amount that may legitimately be zero."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")

    if value < 0:
        raise ValueError(f"{name} cannot be negative")

    return value


def token_id(value: object) -> int:
    """Return a positive LP NFT id."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("token_id must be a positive integer")

    return value


def fee_tier(value: object) -> int:
    """Return a pool fee tier in hundredths of a basis point."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 < value < 1_000_000
    ):
        raise ValueError("fee must be a positive integer below 1000000")

    return value


def token_address(w3: Web3, address: object, name: str) -> str:
    """Return a checksummed token address."""
    if not isinstance(address, str) or not address.strip():
        raise ValueError(f"{name} must be a non-empty string")

    return w3.to_checksum_address(address)


def token_pair(
    w3: Web3,
    token_in: object,
    token_out: object,
) -> tuple[str, str]:
    """Return two distinct checksummed token addresses."""
    token_in = token_address(w3, token_in, "token_in")
    token_out = token_address(w3, token_out, "token_out")

    if token_in == token_out:
        raise ValueError("token_in and token_out must differ")

    return token_in, token_out
