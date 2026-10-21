"""Tests for transaction building and broadcasting."""

from types import SimpleNamespace

from blockchain.tx import build_transaction

ACCOUNT = "0x0000000000000000000000000000000000000001"


class FakeEth:
    """Minimal ``w3.eth`` that records how the nonce was requested."""

    chain_id = 84532
    gas_price = 1_000_000_000

    def __init__(self):
        self.nonce_calls = []

    def get_transaction_count(self, address, block_identifier="latest"):
        self.nonce_calls.append((address, block_identifier))
        return 7


class FakeFunctionCall:
    """Capture the transaction dictionary built for a contract call."""

    def __init__(self):
        self.transaction = None

    def build_transaction(self, transaction):
        self.transaction = transaction
        return transaction


def test_build_transaction_uses_pending_nonce():
    eth = FakeEth()
    w3 = SimpleNamespace(eth=eth)
    call = FakeFunctionCall()

    transaction = build_transaction(
        w3,
        SimpleNamespace(address=ACCOUNT),
        call,
        gas_limit=100_000,
    )

    assert transaction["nonce"] == 7
    assert eth.nonce_calls == [(ACCOUNT, "pending")]
