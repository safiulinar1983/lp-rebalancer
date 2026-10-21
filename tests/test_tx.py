"""Tests for transaction building and broadcasting."""

from types import SimpleNamespace

import pytest

import blockchain.tx as tx
from blockchain.tx import (
    ChainReorganizationError,
    InsufficientNativeBalanceError,
    TransactionTimeoutError,
    TxReceipt,
    build_transaction,
    ensure_native_balance,
    required_native_balance_wei,
    send_transaction,
    verify_receipt,
    wait_for_receipt,
)

ACCOUNT = "0x0000000000000000000000000000000000000001"
BLOCK_HASH = "0x" + "ab" * 32
OTHER_BLOCK_HASH = "0x" + "cd" * 32
TX_HASH = "0x" + "ef" * 32
_UNSET = object()


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


class FakeAccount:
    def __init__(self, address=ACCOUNT):
        self.address = address
        self.signed = []

    def sign_transaction(self, transaction):
        self.signed.append(transaction)
        return SimpleNamespace(raw_transaction=b"signed")


class ReceiptEth:
    """Fake ``w3.eth`` for receipt/confirmation tests."""

    def __init__(
        self,
        *,
        head=101,
        receipt=None,
        current_receipt=_UNSET,
        block=None,
    ):
        self.block_number = head
        self.receipt = receipt if receipt is not None else make_receipt()
        self.current_receipt = (
            self.receipt
            if current_receipt is _UNSET
            else current_receipt
        )
        self.block = {"hash": BLOCK_HASH} if block is None else block
        self.wait_calls = []

    def wait_for_transaction_receipt(self, tx_hash, timeout=None):
        self.wait_calls.append((tx_hash, timeout))
        return self.receipt

    def get_transaction_receipt(self, _tx_hash):
        return self.current_receipt

    def get_block(self, _block_number):
        return self.block


def make_receipt(**overrides):
    receipt = {
        "status": 1,
        "blockNumber": 100,
        "gasUsed": 21_000,
        "blockHash": BLOCK_HASH,
    }
    receipt.update(overrides)
    return receipt


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


def test_required_native_balance_includes_value_and_reserve():
    transaction = {"gas": 100_000, "gasPrice": 1_000_000_000, "value": 5}

    assert required_native_balance_wei(
        transaction,
        min_balance_wei=7,
    ) == 100_000 * 1_000_000_000 + 5 + 7


def test_ensure_native_balance_passes_when_the_wallet_covers_gas():
    w3 = SimpleNamespace(
        eth=SimpleNamespace(get_balance=lambda _address: 10**18)
    )
    transaction = {"gas": 100_000, "gasPrice": 1_000_000_000, "value": 0}

    assert ensure_native_balance(w3, ACCOUNT, transaction) == 10**18


def test_ensure_native_balance_raises_before_signing_when_too_low():
    eth = FakeEth()
    eth.get_balance = lambda _address: 100
    w3 = SimpleNamespace(eth=eth)
    account = FakeAccount()
    call = FakeFunctionCall()

    with pytest.raises(InsufficientNativeBalanceError, match="Native balance"):
        send_transaction(
            w3,
            account,
            call,
            gas_limit=100_000,
        )

    assert account.signed == []


def test_wait_for_receipt_waits_for_the_requested_confirmations():
    eth = ReceiptEth(head=101)
    w3 = SimpleNamespace(eth=eth)

    receipt = wait_for_receipt(
        w3,
        TX_HASH,
        confirmations=2,
        timeout=5,
    )

    assert receipt["blockNumber"] == 100
    assert eth.wait_calls == [(TX_HASH, 5)]


def test_wait_for_receipt_detects_a_disappeared_receipt():
    eth = ReceiptEth(current_receipt=None)
    w3 = SimpleNamespace(eth=eth)

    with pytest.raises(ChainReorganizationError, match="no longer"):
        wait_for_receipt(
            w3,
            TX_HASH,
            confirmations=2,
            timeout=5,
        )


def test_wait_for_receipt_detects_a_changed_block_hash():
    eth = ReceiptEth(block={"hash": OTHER_BLOCK_HASH})
    w3 = SimpleNamespace(eth=eth)

    with pytest.raises(ChainReorganizationError, match="reorganized out"):
        wait_for_receipt(
            w3,
            TX_HASH,
            confirmations=2,
            timeout=5,
        )


def test_wait_for_receipt_times_out_while_waiting_for_confirmations(
    monkeypatch,
):
    eth = ReceiptEth(head=100)
    w3 = SimpleNamespace(eth=eth)
    clock = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(tx.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(tx.time, "sleep", lambda _seconds: None)

    with pytest.raises(TransactionTimeoutError, match="confirmation"):
        wait_for_receipt(
            w3,
            TX_HASH,
            confirmations=2,
            timeout=1,
            poll_interval=0.1,
        )


def test_verify_receipt_accepts_the_canonical_block():
    receipt = TxReceipt(
        tx_hash=TX_HASH,
        status=1,
        block_number=100,
        gas_used=21_000,
        block_hash=BLOCK_HASH,
    )
    w3 = SimpleNamespace(eth=ReceiptEth())

    verify_receipt(w3, receipt)


def test_verify_receipt_rejects_a_reorged_block():
    receipt = TxReceipt(
        tx_hash=TX_HASH,
        status=1,
        block_number=100,
        gas_used=21_000,
        block_hash=BLOCK_HASH,
    )
    w3 = SimpleNamespace(
        eth=ReceiptEth(block={"hash": OTHER_BLOCK_HASH}),
    )

    with pytest.raises(ChainReorganizationError, match="reorganized out"):
        verify_receipt(w3, receipt)
