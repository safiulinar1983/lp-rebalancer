"""PancakeSwap V3 swap quoting and calldata building.

Quoting goes through ``eth_call`` on QuoterV2; this module never sends a
transaction itself, it only prepares calls for ``blockchain.tx``.
"""

from web3 import Web3
from web3.contract.contract import ContractFunction

from blockchain.abis import QUOTER_V2_ABI, SWAP_ROUTER_ABI
from blockchain.call_params import fee_tier, positive_amount, token_pair

# 0 means "no price limit", the usual choice for a rebalancing swap.
ZERO_SQRT_PRICE_LIMIT = 0


class SwapRouter:
    """SwapRouter wrapper with an optional QuoterV2 for price estimates."""

    def __init__(
        self,
        w3: Web3,
        address: str,
        quoter_address: str = "",
    ):
        self.w3 = w3
        self.address = w3.to_checksum_address(address)

        self.contract = w3.eth.contract(
            address=self.address,
            abi=SWAP_ROUTER_ABI,
        )

        self.quoter_address = (
            w3.to_checksum_address(quoter_address) if quoter_address else ""
        )

        self.quoter = (
            w3.eth.contract(
                address=self.quoter_address,
                abi=QUOTER_V2_ABI,
            )
            if self.quoter_address
            else None
        )

    @property
    def can_quote(self) -> bool:
        """True when an on-chain quote is available."""
        return self.quoter is not None

    def quote_exact_input_single(
        self,
        token_in: str,
        token_out: str,
        fee: int,
        amount_in_raw: int,
    ) -> int:
        """Return the on-chain quote for selling ``amount_in_raw`` raw units."""
        if self.quoter is None:
            raise RuntimeError(
                "No quoter address configured: an on-chain swap quote is "
                "unavailable"
            )

        token_in, token_out = token_pair(self.w3, token_in, token_out)

        params = (
            token_in,
            token_out,
            fee_tier(fee),
            positive_amount(amount_in_raw, "amount_in_raw"),
            ZERO_SQRT_PRICE_LIMIT,
        )

        result = self.quoter.functions.quoteExactInputSingle(params).call()

        return int(result[0])

    def build_exact_input_single(
        self,
        token_in: str,
        token_out: str,
        fee: int,
        recipient: str,
        amount_in_raw: int,
        min_amount_out_raw: int,
    ) -> ContractFunction:
        """Return the ``exactInputSingle`` call for a rebalancing swap."""
        token_in, token_out = token_pair(self.w3, token_in, token_out)

        params = (
            token_in,
            token_out,
            fee_tier(fee),
            self.w3.to_checksum_address(recipient),
            positive_amount(amount_in_raw, "amount_in_raw"),
            positive_amount(min_amount_out_raw, "min_amount_out_raw"),
            ZERO_SQRT_PRICE_LIMIT,
        )

        return self.contract.functions.exactInputSingle(params)
