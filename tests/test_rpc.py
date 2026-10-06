from unittest.mock import MagicMock, patch

from blockchain.rpc import BaseRpcClient


def test_chain_id():
    client = BaseRpcClient("https://example.invalid")
    fake_web3 = MagicMock()
    fake_web3.is_connected.return_value = True
    fake_web3.eth.chain_id = 8453

    with patch.object(client, "_web3", fake_web3):
        assert client.chain_id() == 8453


def test_block_number():
    client = BaseRpcClient("https://example.invalid")
    fake_web3 = MagicMock()
    fake_web3.is_connected.return_value = True
    fake_web3.eth.block_number = 12345678

    with patch.object(client, "_web3", fake_web3):
        assert client.block_number() == 12345678
