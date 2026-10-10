from unittest.mock import MagicMock

import pytest

from blockchain.dex_manager import DEXManager


def test_creates_pancakeswap_v3_adapter(monkeypatch):
    expected_pool = MagicMock()
    constructor = MagicMock(return_value=expected_pool)

    monkeypatch.setattr(
        "blockchain.dex_manager.PancakeV3Pool",
        constructor,
    )

    w3 = MagicMock()
    address = "0x0000000000000000000000000000000000000001"

    pool = DEXManager.create_pool(
        dex_name="pancakeswap_v3",
        w3=w3,
        pool_address=address,
    )

    assert pool is expected_pool
    constructor.assert_called_once_with(w3=w3, address=address)


def test_dex_name_is_case_insensitive(monkeypatch):
    expected_pool = MagicMock()
    constructor = MagicMock(return_value=expected_pool)

    monkeypatch.setattr(
        "blockchain.dex_manager.PancakeV3Pool",
        constructor,
    )

    pool = DEXManager.create_pool(
        dex_name="PancakeSwap_V3",
        w3=MagicMock(),
        pool_address="0x0000000000000000000000000000000000000001",
    )

    assert pool is expected_pool


def test_rejects_unsupported_dex():
    with pytest.raises(ValueError, match="Unsupported DEX"):
        DEXManager.create_pool(
            dex_name="unknown_dex",
            w3=MagicMock(),
            pool_address="0x0000000000000000000000000000000000000001",
        )
