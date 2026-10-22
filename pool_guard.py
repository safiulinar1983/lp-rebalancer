"""Guard against pointing the bot at a different pool than the config claims.

Switching pools is a config-only operation: ``dexes.<dex>.pool.address`` plus a
Chainlink feed per pool token. A typo in that address would otherwise surface
only after the bot has priced an unrelated pair and prepared a transaction for
it. The optional ``pool.expected_fee``, ``pool.expected_token0`` and
``pool.expected_token1`` values are compared with the state read from the chain
before any pricing, planning or signing happens.

The guard is opt-in per field: an empty expectation is not checked, so a
project can add it one value at a time. Tokens are compared positionally, in
the order the pool itself returns them (``scripts/monitor_pool.py`` prints that
order); addresses are compared case-insensitively.
"""

from blockchain.interfaces import PoolAdapter
from blockchain.pancake_v3 import PoolState
from config import AppConfig


def _pool_mismatches(state: PoolState, config: AppConfig) -> list[str]:
    """Return one description per configured expectation the pool violates."""
    mismatches: list[str] = []

    if (
        config.pool_expected_fee is not None
        and state.fee != config.pool_expected_fee
    ):
        mismatches.append(
            f"fee is {state.fee}, expected {config.pool_expected_fee}"
        )

    for label, expected, actual in (
        ("token0", config.pool_expected_token0, state.token0),
        ("token1", config.pool_expected_token1, state.token1),
    ):
        if expected and expected.lower() != actual.lower():
            mismatches.append(f"{label} is {actual}, expected {expected}")

    return mismatches


def verify_pool_state(state: PoolState, config: AppConfig) -> None:
    """Raise ``ValueError`` when the on-chain pool contradicts the config.

    The message names the configured pool path and both sides of every
    mismatch, so a wrong ``pool.address`` (or a forgotten expectation after a
    switch) is fixed from the error alone.
    """
    mismatches = _pool_mismatches(state, config)

    if not mismatches:
        return

    details = "; ".join(mismatches)
    raise ValueError(
        f"Pool {state.address} does not match dexes.{config.dex}.pool "
        f"({details}). Check pool.address and the expected_* guards"
    )


def read_pool_state(pool: PoolAdapter, config: AppConfig) -> PoolState:
    """Read the pool state once and verify it against the configuration."""
    state = pool.read_state()
    verify_pool_state(state, config)
    return state
