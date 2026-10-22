"""Tests for ``pool_guard``: the optional ``pool.expected_*`` switch guards.

Switching pools is a config-only edit, so a typo in ``pool.address`` must stop
the bot before any price is resolved or a transaction is prepared, and the
error must name both sides of the mismatch.
"""

from dataclasses import replace
from decimal import Decimal

import pytest

from blockchain.liquidity_math import Q96
from blockchain.pancake_v3 import PoolState
from config import load_config
from pool_guard import read_pool_state, verify_pool_state

WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
CBBTC = "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf"


def make_state(**overrides) -> PoolState:
    values = {
        "address": "0xd0b53D9277642d899DF5C87A3966A349A798F224",
        "token0": WETH,
        "token1": USDC,
        "token0_decimals": 18,
        "token1_decimals": 6,
        "fee": 500,
        "tick_spacing": 10,
        "sqrt_price_x96": int(Q96),
        "tick": 0,
        "liquidity": 1_000_000,
        "price": Decimal("1"),
    }
    values.update(overrides)
    return PoolState(**values)


def make_config(**overrides):
    """Mainnet config with the guards set to the WETH/USDC pool."""
    values = {
        "pool_expected_fee": 500,
        "pool_expected_token0": WETH,
        "pool_expected_token1": USDC,
    }
    values.update(overrides)
    return replace(load_config(), **values)


class FakePool:
    """Minimal ``PoolAdapter`` that records how often it was read."""

    def __init__(self, state: PoolState):
        self._state = state
        self.read_count = 0

    def read_state(self) -> PoolState:
        self.read_count += 1
        return self._state


def test_matching_pool_passes():
    verify_pool_state(make_state(), make_config())


def test_addresses_are_compared_case_insensitively():
    config = make_config(
        pool_expected_token0=WETH.lower(),
        pool_expected_token1=USDC.lower(),
    )

    verify_pool_state(make_state(), config)


def test_wrong_fee_is_reported():
    with pytest.raises(ValueError, match=r"fee is 3000, expected 500"):
        verify_pool_state(
            make_state(fee=3000),
            make_config(),
        )


def test_wrong_token_is_reported_with_the_config_path():
    with pytest.raises(ValueError) as excinfo:
        verify_pool_state(
            make_state(token1=CBBTC),
            make_config(),
        )

    message = str(excinfo.value)
    assert "dexes.uniswap_v3.pool" in message
    assert f"token1 is {CBBTC}, expected {USDC}" in message


def test_every_mismatch_is_reported_at_once():
    with pytest.raises(ValueError) as excinfo:
        verify_pool_state(
            make_state(token0=USDC, token1=WETH, fee=100),
            make_config(),
        )

    message = str(excinfo.value)
    assert "fee is 100, expected 500" in message
    assert f"token0 is {USDC}, expected {WETH}" in message
    assert f"token1 is {WETH}, expected {USDC}" in message


def test_unset_guards_are_not_checked():
    config = make_config(
        pool_expected_fee=None,
        pool_expected_token0="",
        pool_expected_token1="",
    )

    verify_pool_state(make_state(token0=CBBTC, token1=USDC, fee=100), config)


def test_only_the_configured_guards_are_checked():
    config = make_config(
        pool_expected_token1="",
        pool_expected_token0=CBBTC,
    )

    with pytest.raises(ValueError, match="token0 is"):
        verify_pool_state(make_state(fee=100), config)


def test_read_pool_state_returns_the_verified_state():
    pool = FakePool(make_state())

    state = read_pool_state(pool, make_config())

    assert state.token0 == WETH
    assert pool.read_count == 1


def test_read_pool_state_rejects_a_foreign_pool():
    pool = FakePool(make_state(token0=CBBTC))

    with pytest.raises(ValueError, match="does not match"):
        read_pool_state(pool, make_config())

    assert pool.read_count == 1
