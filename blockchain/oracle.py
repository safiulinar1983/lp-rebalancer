import time
from decimal import Decimal

from web3 import Web3


CHAINLINK_ABI = [
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
    {
        "name": "latestRoundData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [
            {"name": "roundId", "type": "uint80"},
            {"name": "answer", "type": "int256"},
            {"name": "startedAt", "type": "uint256"},
            {"name": "updatedAt", "type": "uint256"},
            {"name": "answeredInRound", "type": "uint80"},
        ],
    },
]


def get_token_price_usd(
    w3: Web3,
    feed_address: str,
    max_age_seconds: int = 3600,
) -> Decimal:
    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")

    if not Web3.is_address(feed_address):
        raise ValueError("Invalid Chainlink feed address")

    feed = w3.eth.contract(
        address=Web3.to_checksum_address(feed_address),
        abi=CHAINLINK_ABI,
    )

    decimals = feed.functions.decimals().call()
    _, answer, _, updated_at, _ = (
        feed.functions.latestRoundData().call()
    )

    if answer <= 0:
        raise ValueError("Chainlink returned an invalid price")

    now = time.time()
    if updated_at <= 0 or updated_at > now:
        raise ValueError("Chainlink returned an invalid timestamp")

    if now - updated_at > max_age_seconds:
        raise ValueError("Chainlink price is stale")

    return Decimal(answer) / (Decimal(10) ** decimals)
