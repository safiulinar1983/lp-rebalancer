"""Tests for DEX-specific swap router calldata.

The QuoterV2 struct and the two router structs share field names but not field
order. These tests pin the exact calldata so a wrong order cannot silently
reach ``eth_call`` or a signed transaction again.
"""

from types import SimpleNamespace

import pytest
from eth_abi import decode
from web3 import Web3

from blockchain.swap_router import SwapRouter

TOKEN_IN = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
TOKEN_OUT = "0x4200000000000000000000000000000000000006"
RECIPIENT = "0x87e58e8B5983FC4fF8199d3E16264ad39182a96e"
ROUTER = "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4"
QUOTER = "0xC5290058841028F1614F3A6F0F5816cAd0df5E27"
FEE = 500
AMOUNT_IN = 1_000_000
MIN_AMOUNT_OUT = 990_000

UNISWAP_SELECTOR = bytes.fromhex("04e45aaf")
PANCAKE_SELECTOR = bytes.fromhex("414bf389")


def calldata(function_call) -> bytes:
    """Return the calldata a transaction would carry."""
    data = function_call._encode_transaction_data()

    # web3 v7 returns a hex string here; older releases return bytes.
    return bytes.fromhex(data[2:]) if isinstance(data, str) else data


def normalized(values) -> tuple:
    """Lowercase addresses so checksum casing does not affect comparisons."""
    return tuple(
        value.lower() if isinstance(value, str) else value
        for value in values
    )


def test_quote_passes_amount_in_before_fee():
    router = SwapRouter(
        Web3(),
        ROUTER,
        quoter_address=QUOTER,
        dex="uniswap_v3",
    )

    captured = {}

    def quote(params):
        captured["params"] = params
        return SimpleNamespace(call=lambda: (123, 0, 0, 0))

    router.quoter = SimpleNamespace(
        functions=SimpleNamespace(quoteExactInputSingle=quote)
    )

    amount_out = router.quote_exact_input_single(
        TOKEN_IN,
        TOKEN_OUT,
        FEE,
        AMOUNT_IN,
    )

    assert amount_out == 123
    assert captured["params"] == (TOKEN_IN, TOKEN_OUT, AMOUNT_IN, FEE, 0)


def test_uniswap_calldata_uses_swap_router02_struct():
    router = SwapRouter(Web3(), ROUTER, dex="uniswap_v3")

    data = calldata(
        router.build_exact_input_single(
            TOKEN_IN,
            TOKEN_OUT,
            FEE,
            RECIPIENT,
            AMOUNT_IN,
            MIN_AMOUNT_OUT,
        )
    )

    assert data[:4] == UNISWAP_SELECTOR
    assert normalized(
        decode(
            [
                "address",
                "address",
                "uint24",
                "address",
                "uint256",
                "uint256",
                "uint160",
            ],
            data[4:],
        )
    ) == normalized(
        (
            TOKEN_IN,
            TOKEN_OUT,
            FEE,
            RECIPIENT,
            AMOUNT_IN,
            MIN_AMOUNT_OUT,
            0,
        )
    )


def test_pancake_calldata_encodes_deadline_after_recipient(monkeypatch):
    monkeypatch.setattr(
        "blockchain.swap_router.time.time",
        lambda: 1_700_000_000,
    )

    router = SwapRouter(Web3(), ROUTER, dex="pancakeswap_v3")

    data = calldata(
        router.build_exact_input_single(
            TOKEN_IN,
            TOKEN_OUT,
            FEE,
            RECIPIENT,
            AMOUNT_IN,
            MIN_AMOUNT_OUT,
        )
    )

    assert data[:4] == PANCAKE_SELECTOR
    assert normalized(
        decode(
            [
                "address",
                "address",
                "uint24",
                "address",
                "uint256",
                "uint256",
                "uint256",
                "uint160",
            ],
            data[4:],
        )
    ) == normalized(
        (
            TOKEN_IN,
            TOKEN_OUT,
            FEE,
            RECIPIENT,
            1_700_000_300,
            AMOUNT_IN,
            MIN_AMOUNT_OUT,
            0,
        )
    )


def test_pancake_accepts_explicit_deadline():
    router = SwapRouter(Web3(), ROUTER, dex="pancakeswap_v3")

    data = calldata(
        router.build_exact_input_single(
            TOKEN_IN,
            TOKEN_OUT,
            FEE,
            RECIPIENT,
            AMOUNT_IN,
            MIN_AMOUNT_OUT,
            deadline=1_800_000_000,
        )
    )

    assert decode(
        ["uint256"],
        data[4 + 32 * 4 : 4 + 32 * 5],
    ) == (1_800_000_000,)


def test_uniswap_rejects_deadline():
    router = SwapRouter(Web3(), ROUTER, dex="uniswap_v3")

    with pytest.raises(ValueError, match="does not accept a deadline"):
        router.build_exact_input_single(
            TOKEN_IN,
            TOKEN_OUT,
            FEE,
            RECIPIENT,
            AMOUNT_IN,
            MIN_AMOUNT_OUT,
            deadline=1_800_000_000,
        )


def test_rejects_unsupported_dex():
    with pytest.raises(ValueError, match="Unsupported DEX"):
        SwapRouter(Web3(), ROUTER, dex="unknown_dex")


def test_rejects_non_positive_deadline_window():
    with pytest.raises(ValueError, match="deadline_seconds"):
        SwapRouter(
            Web3(),
            ROUTER,
            dex="pancakeswap_v3",
            deadline_seconds=0,
        )


def test_quote_requires_a_quoter():
    router = SwapRouter(Web3(), ROUTER, dex="uniswap_v3")

    with pytest.raises(RuntimeError, match="quoter.address"):
        router.quote_exact_input_single(
            TOKEN_IN,
            TOKEN_OUT,
            FEE,
            AMOUNT_IN,
        )