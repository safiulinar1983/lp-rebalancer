"""Signing and broadcasting of prepared contract calls.

Calldata is built by the adapters (``blockchain.position_manager``,
``blockchain.swap_router``); this module only adds the gas parameters, signs,
broadcasts and waits for the receipt, so transaction plumbing lives in exactly
one place.
"""

from dataclasses import dataclass
from typing import Any

from web3 import Web3
from web3.contract.contract import ContractFunction


@dataclass(frozen=True)
class TxReceipt:
    """Outcome of a confirmed transaction."""

    tx_hash: str
    status: int
    block_number: int
    gas_used: int

    @property
    def confirmed(self) -> bool:
        return self.status == 1


def _validate_positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")

    return value


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
) -> TxReceipt:
    """Sign, broadcast and confirm ``function_call``.

    Raises ``RuntimeError`` when the transaction is reverted on chain, so a
    failure can never be mistaken for a successful step.
    """
    transaction = build_transaction(
        w3,
        account,
        function_call,
        gas_limit=gas_limit,
        value=value,
        gas_price=gas_price,
    )

    signed = account.sign_transaction(transaction)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    result = TxReceipt(
        tx_hash=tx_hash.hex(),
        status=int(receipt["status"]),
        block_number=int(receipt["blockNumber"]),
        gas_used=int(receipt["gasUsed"]),
    )

    if not result.confirmed:
        raise RuntimeError(
            f"Transaction {result.tx_hash} was reverted on chain"
        )

    return result
