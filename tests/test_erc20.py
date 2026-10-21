"""Tests for the ERC20 allowance helpers."""

import pytest
from eth_abi import decode
from web3 import Web3

from blockchain.erc20 import MAX_UINT256, ERC20Token

TOKEN = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
SPENDER = "0x27F971cb582BF9E50F397e4d29a5C7A34f11faA2"


def calldata(function_call) -> bytes:
    """Return the calldata a transaction would carry."""
    data = function_call._encode_transaction_data()

    # web3 v7 returns a hex string here; older releases return bytes.
    return bytes.fromhex(data[2:]) if isinstance(data, str) else data


def test_build_max_approve_grants_unlimited_allowance():
    token = ERC20Token(Web3(), TOKEN)

    data = calldata(token.build_max_approve(SPENDER))

    assert data[:4] == Web3.keccak(text="approve(address,uint256)")[:4]

    spender, amount = decode(["address", "uint256"], data[4:])

    assert spender == SPENDER.lower()
    assert amount == MAX_UINT256


def test_build_max_approve_rejects_empty_spender():
    token = ERC20Token(Web3(), TOKEN)

    with pytest.raises(ValueError, match="spender"):
        token.build_max_approve("")


def test_zero_amount_needs_no_approval():
    token = ERC20Token(Web3(), TOKEN)

    assert token.needs_approval(SPENDER, SPENDER, 0) is False