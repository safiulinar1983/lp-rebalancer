"""Minimal ERC20 helper for allowances and wallet balances.

The rebalance cycle must know whether the swap router and the position manager
are allowed to pull the tokens it is about to spend: a missing allowance would
otherwise turn into a reverted transaction.
"""

from web3 import Web3
from web3.contract.contract import ContractFunction

from blockchain.abis import ERC20_ABI
from blockchain.call_params import non_negative_amount, positive_amount

# Unlimited allowance: grants the spender a one-time approval instead of an
# exact amount that has to be renewed on every rebalance.
MAX_UINT256 = 2**256 - 1


class ERC20Token:
    """Read balances/allowances and prepare ``approve`` calls."""

    def __init__(self, w3: Web3, address: str):
        self.w3 = w3
        self.address = w3.to_checksum_address(address)

        self.contract = w3.eth.contract(
            address=self.address,
            abi=ERC20_ABI,
        )

    def balance_of(self, owner: str) -> int:
        """Return the raw token balance of ``owner``."""
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError("owner must be a non-empty string")

        return int(
            self.contract.functions.balanceOf(
                self.w3.to_checksum_address(owner)
            ).call()
        )

    def allowance(self, owner: str, spender: str) -> int:
        """Return the raw amount ``spender`` may pull from ``owner``."""
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError("owner must be a non-empty string")

        if not isinstance(spender, str) or not spender.strip():
            raise ValueError("spender must be a non-empty string")

        return int(
            self.contract.functions.allowance(
                self.w3.to_checksum_address(owner),
                self.w3.to_checksum_address(spender),
            ).call()
        )

    def needs_approval(self, owner: str, spender: str, amount: int) -> bool:
        """Return True when an ``approve`` call is required for ``amount``."""
        amount = non_negative_amount(amount, "amount")

        if amount == 0:
            return False

        return self.allowance(owner, spender) < amount

    def build_approve(self, spender: str, amount: int) -> ContractFunction:
        """Return the ``approve`` call granting ``amount`` to ``spender``."""
        if not isinstance(spender, str) or not spender.strip():
            raise ValueError("spender must be a non-empty string")

        return self.contract.functions.approve(
            self.w3.to_checksum_address(spender),
            positive_amount(amount, "amount"),
        )

    def build_max_approve(self, spender: str) -> ContractFunction:
        """Return an ``approve`` call granting an unlimited allowance."""
        return self.build_approve(spender, MAX_UINT256)
