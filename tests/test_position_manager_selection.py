from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from blockchain.position_manager import PositionManager
from strategy import Position


TOKEN0 = "0x0000000000000000000000000000000000000001"
TOKEN1 = "0x0000000000000000000000000000000000000002"
WALLET = "0x0000000000000000000000000000000000000003"
OTHER = "0x0000000000000000000000000000000000000004"


def make_position_manager(owner=WALLET, position=None):
    manager = PositionManager.__new__(PositionManager)

    manager.w3 = SimpleNamespace(
        to_checksum_address=lambda address: address
    )
    manager.wallet = WALLET

    owner_call = Mock(return_value=owner)

    manager.contract = SimpleNamespace(
        functions=SimpleNamespace(
            ownerOf=Mock(return_value=SimpleNamespace(call=owner_call))
        )
    )

    if position is None:
        position = Position(
            token_id=82740,
            token0=TOKEN0,
            token1=TOKEN1,
            fee=500,
            lower_tick=219000,
            upper_tick=219200,
            liquidity=1000,
            tokens_owed0=0,
            tokens_owed1=0,
        )

    manager.read_position = Mock(return_value=position)
    manager.get_token_ids = Mock(return_value=[82740])

    return manager


def test_explicit_token_id_returns_requested_position():
    manager = make_position_manager()

    result = manager.find_position(
        token0=TOKEN0,
        token1=TOKEN1,
        fee=500,
        token_id=82740,
    )

    assert result.token_id == 82740
    manager.contract.functions.ownerOf.assert_called_once_with(82740)
    manager.read_position.assert_called_once_with(82740)
    manager.get_token_ids.assert_not_called()


def test_explicit_token_id_rejects_position_owned_by_other_wallet():
    manager = make_position_manager(owner=OTHER)

    with pytest.raises(RuntimeError, match="not configured wallet"):
        manager.find_position(
            token0=TOKEN0,
            token1=TOKEN1,
            fee=500,
            token_id=82740,
        )

    manager.read_position.assert_not_called()


@pytest.mark.parametrize(
    ("token0", "token1", "fee"),
    [
        ("0x0000000000000000000000000000000000000009", TOKEN1, 500),
        (TOKEN0, "0x0000000000000000000000000000000000000009", 500),
        (TOKEN0, TOKEN1, 3000),
    ],
)
def test_explicit_token_id_rejects_wrong_pool(token0, token1, fee):
    manager = make_position_manager()

    with pytest.raises(RuntimeError, match="does not match"):
        manager.find_position(
            token0=token0,
            token1=token1,
            fee=fee,
            token_id=82740,
        )


@pytest.mark.parametrize("token_id", [0, -1, True, 1.5, "82740"])
def test_explicit_token_id_rejects_invalid_id(token_id):
    manager = make_position_manager()

    with pytest.raises(ValueError, match="token_id"):
        manager.find_position(
            token0=TOKEN0,
            token1=TOKEN1,
            fee=500,
            token_id=token_id,
        )
