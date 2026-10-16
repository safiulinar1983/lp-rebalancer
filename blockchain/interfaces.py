"""Protocols shared by the blockchain adapters.

``PoolAdapter`` is checked structurally: any object exposing ``read_state``
returning a ``PoolState`` satisfies it (see ``blockchain.pancake_v3``).
"""

from typing import Protocol

from blockchain.pancake_v3 import PoolState


class PoolAdapter(Protocol):
    """Read-only interface for a concentrated-liquidity DEX pool."""

    def read_state(self) -> PoolState:
        """Return the current pool state."""
        ...
