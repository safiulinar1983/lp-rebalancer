from typing import Protocol

from blockchain.pancake_v3 import PoolState


class PoolAdapter(Protocol):
    """Read-only interface for a concentrated-liquidity DEX pool."""

    def read_state(self) -> PoolState:
        """Return the current pool state."""
        ...
