"""Signing and broadcasting of prepared contract calls.

Calldata is built by the adapters (``blockchain.position_manager``,
``blockchain.swap_router``); this module only adds the gas parameters, signs,
broadcasts and waits for the receipt, so transaction plumbing lives in exactly
one place.

Before a transaction is signed, the native balance is checked against the
worst-case gas cost plus the configured reserve. After broadcast the receipt is
waited for, allowed to gather confirmations and then re-checked against the
canonical chain. A reorg or a timeout makes the on-chain outcome unknown, so
these errors are deliberately *unsafe*: the caller must not simply retry.
"""

import time
from dataclasses import dataclass
from typing import Any

from web3 import Web3
from web3.contract.contract import ContractFunction
from web3.exceptions import TimeExhausted

DEFAULT_CONFIRMATIONS = 2
DEFAULT_RECEIPT_TIMEOUT_SECONDS = 180
DEFAULT_POLL_INTERVAL_SECONDS = 1.0


@dataclass(frozen=True)
class TxReceipt:
    """Outcome of a confirmed transaction."""

    tx_hash: str
    status: int
    block_number: int
    gas_used: int
    block_hash: str | None = None

    @property
    def confirmed(self) -> bool:
        return self.status == 1


class TransactionError(RuntimeError):
    """Base class for transaction plumbing errors."""


class InsufficientNativeBalanceError(TransactionError):
    """Raised before signing when the wallet cannot cover gas plus reserve."""


class UnsafeTransactionError(TransactionError):
    """The on-chain outcome is unknown; retrying could duplicate the action."""


class TransactionTimeoutError(UnsafeTransactionError):
    """The transaction was broadcast but did not gather enough confirmations."""


class ChainReorganizationError(UnsafeTransactionError):
    """A previously confirmed transaction is no longer on the canonical chain."""


def _validate_positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")

    return value


def _validate_non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")

    return value


def _validate_positive_number(value: object, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value <= 0
    ):
        raise ValueError(f"{name} must be a positive number")

    return float(value)


def _field(value: Any, key: str) -> Any:
    """Read a field from a Web3 AttributeDict or a plain mapping."""
    if value is None:
        return None

    if hasattr(value, "get"):
        return value.get(key)

    return getattr(value, key, None)


def _hex(value: Any) -> str | None:
    if value is None:
        return None

    if hasattr(value, "hex"):
        return str(value.hex())

    return str(value)


def build_transaction(
    w3: Web3,
    account: Any,
    function_call: ContractFunction,
    *,
    gas_limit: int,
    value: int = 0,
    gas_price: int | None = None,
) -> dict[str, Any]:
    """Build a signed-ready transaction for ``function_call``."""
    gas_limit = _validate_positive_int(gas_limit, "gas_limit")

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("value must be a non-negative integer")

    if gas_price is not None:
        gas_price = _validate_positive_int(gas_price, "gas_price")

    return function_call.build_transaction(
        {
            "from": account.address,
            "value": value,
            # Include transactions that are already broadcast but not mined
            # yet: reading the latest nonce can return the one just consumed
            # when the RPC has not caught up, which makes the next send look
            # like an underpriced replacement.
            "nonce": w3.eth.get_transaction_count(
                account.address,
                "pending",
            ),
            "chainId": w3.eth.chain_id,
            "gas": gas_limit,
            "gasPrice": w3.eth.gas_price if gas_price is None else gas_price,
        }
    )


def required_native_balance_wei(
    transaction: dict[str, Any],
    *,
    min_balance_wei: int = 0,
) -> int:
    """Return the balance needed to send ``transaction`` and keep a reserve.

    The gas limit, not the expected gas usage, is used: the transaction may
    consume all of it. ``min_balance_wei`` is the amount that must remain in
    the wallet after the transaction, so it is added to the requirement.
    """
    min_balance_wei = _validate_non_negative_int(
        min_balance_wei,
        "min_balance_wei",
    )
    gas = _validate_positive_int(transaction.get("gas"), "transaction.gas")
    gas_price = _validate_positive_int(
        transaction.get("gasPrice"),
        "transaction.gasPrice",
    )
    value = _validate_non_negative_int(
        transaction.get("value", 0),
        "transaction.value",
    )

    return gas * gas_price + value + min_balance_wei


def ensure_native_balance(
    w3: Web3,
    address: str,
    transaction: dict[str, Any],
    *,
    min_balance_wei: int = 0,
) -> int:
    """Check the native balance before signing, returning the current balance."""
    if not isinstance(address, str) or not address.strip():
        raise ValueError("address must be a non-empty string")

    required_wei = required_native_balance_wei(
        transaction,
        min_balance_wei=min_balance_wei,
    )
    balance_wei = int(w3.eth.get_balance(address))

    if balance_wei < required_wei:
        raise InsufficientNativeBalanceError(
            f"Native balance {balance_wei} wei of {address} is below the "
            f"required {required_wei} wei "
            "(gas limit * gas price + value + configured reserve)"
        )

    return balance_wei


def _verify_canonical_block(
    w3: Web3,
    tx_hash: Any,
    block_number: int,
    block_hash: str,
) -> None:
    """Raise ``ChainReorganizationError`` if the receipt left the canon chain."""
    receipt = w3.eth.get_transaction_receipt(tx_hash)

    if receipt is None:
        raise ChainReorganizationError(
            f"Transaction {_hex(tx_hash)} is no longer in the canonical chain"
        )

    current_block_hash = _hex(_field(receipt, "blockHash"))
    current_block_number = _field(receipt, "blockNumber")

    if (
        current_block_hash != block_hash
        or current_block_number is None
        or int(current_block_number) != block_number
    ):
        raise ChainReorganizationError(
            f"Transaction {_hex(tx_hash)} moved from block {block_number} "
            f"({block_hash}) to block {current_block_number} "
            f"({current_block_hash})"
        )

    block = w3.eth.get_block(block_number)

    if block is None or _hex(_field(block, "hash")) != block_hash:
        raise ChainReorganizationError(
            f"Block {block_number} no longer has hash {block_hash}; "
            f"transaction {_hex(tx_hash)} was reorganized out"
        )


def verify_receipt(w3: Web3, receipt: TxReceipt) -> None:
    """Re-check that a confirmed receipt is still on the canonical chain.

    Receipts built by tests or older callers without ``block_hash`` cannot be
    checked and are accepted as-is.
    """
    if not isinstance(receipt, TxReceipt):
        raise ValueError("receipt must be a TxReceipt")

    if receipt.block_hash is None:
        return

    _verify_canonical_block(
        w3,
        receipt.tx_hash,
        receipt.block_number,
        receipt.block_hash,
    )


def wait_for_receipt(
    w3: Web3,
    tx_hash: Any,
    *,
    confirmations: int = DEFAULT_CONFIRMATIONS,
    timeout: int = DEFAULT_RECEIPT_TIMEOUT_SECONDS,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> Any:
    """Wait for a receipt, ``confirmations`` blocks and a canonical check.

    ``confirmations=2`` means one block mined after the inclusion block, which
    gives a single-block reorg a chance to be observed before the next cycle
    step is sent.
    """
    confirmations = _validate_positive_int(
        confirmations,
        "confirmations",
    )
    timeout = _validate_positive_number(timeout, "timeout")
    poll_interval = _validate_positive_number(
        poll_interval,
        "poll_interval",
    )
    deadline = time.monotonic() + timeout

    try:
        receipt = w3.eth.wait_for_transaction_receipt(
            tx_hash,
            timeout=timeout,
        )
    except TimeExhausted as exc:
        raise TransactionTimeoutError(
            f"Transaction {_hex(tx_hash)} was not mined within {timeout}s"
        ) from exc

    if receipt is None:
        raise TransactionTimeoutError(
            f"Transaction {_hex(tx_hash)} returned no receipt within {timeout}s"
        )

    block_number = _field(receipt, "blockNumber")
    block_hash = _hex(_field(receipt, "blockHash"))

    if block_number is None or block_hash is None:
        raise TransactionError(
            f"Receipt of transaction {_hex(tx_hash)} has no block number/hash"
        )

    block_number = int(block_number)
    target_block = block_number + confirmations - 1

    while True:
        head = int(w3.eth.block_number)

        if head >= target_block:
            break

        if time.monotonic() >= deadline:
            raise TransactionTimeoutError(
                f"Transaction {_hex(tx_hash)} was mined in block "
                f"{block_number}, but only block {head} is available; "
                f"{confirmations} confirmation(s) were not reached in "
                f"{timeout}s"
            )

        time.sleep(poll_interval)

    _verify_canonical_block(w3, tx_hash, block_number, block_hash)
    return receipt


def simulate(function_call: ContractFunction, from_address: str) -> Any:
    """Execute ``function_call`` through ``eth_call`` without sending it."""
    if not isinstance(from_address, str) or not from_address.strip():
        raise ValueError("from_address must be a non-empty string")

    return function_call.call({"from": from_address})


def send_transaction(
    w3: Web3,
    account: Any,
    function_call: ContractFunction,
    *,
    gas_limit: int,
    value: int = 0,
    gas_price: int | None = None,
    min_balance_wei: int = 0,
    confirmations: int = DEFAULT_CONFIRMATIONS,
    timeout: int = DEFAULT_RECEIPT_TIMEOUT_SECONDS,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> TxReceipt:
    """Sign, broadcast and confirm ``function_call``.

    The native balance is checked against the worst-case gas cost before
    signing. After broadcast the receipt is awaited, confirmed and verified
    against the canonical chain.

    Raises ``RuntimeError`` when the transaction is reverted on chain, so a
    failure can never be mistaken for a successful step. Reorgs and timeouts
    raise subclasses of ``UnsafeTransactionError``: their outcome is unknown
    and the caller must stop instead of retrying blindly.
    """
    transaction = build_transaction(
        w3,
        account,
        function_call,
        gas_limit=gas_limit,
        value=value,
        gas_price=gas_price,
    )

    ensure_native_balance(
        w3,
        account.address,
        transaction,
        min_balance_wei=min_balance_wei,
    )

    signed = account.sign_transaction(transaction)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = wait_for_receipt(
        w3,
        tx_hash,
        confirmations=confirmations,
        timeout=timeout,
        poll_interval=poll_interval,
    )

    result = TxReceipt(
        tx_hash=tx_hash.hex(),
        status=int(receipt["status"]),
        block_number=int(receipt["blockNumber"]),
        gas_used=int(receipt["gasUsed"]),
        block_hash=_hex(_field(receipt, "blockHash")),
    )

    if not result.confirmed:
        raise RuntimeError(
            f"Transaction {result.tx_hash} was reverted on chain"
        )

    return result
