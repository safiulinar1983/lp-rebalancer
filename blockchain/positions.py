"""LP position model shared by the strategy and the on-chain readers.

The dataclass lives in the blockchain layer so that readers such as
``blockchain.position_manager`` do not depend on ``strategy``.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    """A concentrated-liquidity LP position (PancakeSwap V3 NFT)."""

    token_id: int
    token0: str
    token1: str
    fee: int
    lower_tick: int
    upper_tick: int
    liquidity: int
    tokens_owed0: int
    tokens_owed1: int
