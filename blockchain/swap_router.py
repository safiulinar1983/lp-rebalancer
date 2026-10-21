"""V3 swap quoting and calldata building for Uniswap V3 and PancakeSwap V3.

Both DEXes expose the same QuoterV2 interface, but their routers differ:
Uniswap SwapRouter02 takes a struct without a deadline, while PancakeSwap's
SwapRouter adds a deadline field. The DEX name selects the router ABI, so a
router address is never paired with the wrong struct layout.

Quoting goes through ``eth_call`` on QuoterV2; this module never sends a
transaction itself, it only prepares calls for ``blockchain.tx``.
"""

import time

from web3 import Web3
from web3.contract.contract import ContractFunction

from blockchain.abis import (
    PANCAKESWAP_V3_SWAP_ROUTER_ABI,
    QUOTER_V2_ABI,
    UNISWAP_V3_SWAP_ROUTER_ABI,
)
from blockchain.call_params import fee_tier, positive_amount, token_pair

# 0 means "no price limit", the usual choice for a rebalancing swap.
ZERO_SQRT_PRICE_LIMIT = 0

# A swap stays valid for five minutes unless the caller passes its own
# deadline.
DEFAULT_SWAP_DEADLINE_SECONDS = 300

# Router ABIs differ between DEXes even though the function name is the same.
SWAP_ROUTER_ABIS = {
    "uniswap_v3": UNISWAP_V3_SWAP_ROUTER_ABI,
    "pancakeswap_v3": PANCAKESWAP_V3_SWAP_ROUTER_ABI,
}

# Only PancakeSwap's router carries the extra deadline field.
DEADLINE_DEXES = frozenset({"pancakeswap_v3"})


class SwapRouter:
    """SwapRouter wrapper with an optional QuoterV2 for price estimates."""

    def __init__(
        self,
        w3: Web3,
        address: str,
        quoter_address: str = "",
        dex: str = "pancakeswap_v3",
        deadline_seconds: int = DEFAULT_SWAP_DEADLINE_SECONDS,
    ):
        self.w3 = w3
        self.address = w3.to_checksum_address(address)

        dex_name = str(dex).strip().lower()

        if dex_name not in SWAP_ROUTER_ABIS:
            supported = ", ".join(sorted(SWAP_ROUTER_ABIS))
            raise ValueError(
                f"Unsupported DEX: {dex!r}. Supported DEXes: {supported}"
            )

        if (
            isinstance(deadline_seconds, bool)
            or not isinstance(deadline_seconds, int)
            or deadline_seconds <= 0
        ):
            raise ValueError("deadline_seconds must be a positive integer")

        self.dex = dex_name
        self.deadline_seconds = deadline_seconds

        self.contract = w3.eth.contract(
            address=self.address,
            abi=SWAP_ROUTER_ABIS[dex_name],
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

        # QuoterV2 takes (tokenIn, tokenOut, amountIn, fee, sqrtPriceLimitX96):
        # the amount comes before the fee tier, unlike the router struct.
        params = (
            token_in,
            token_out,
            positive_amount(amount_in_raw, "amount_in_raw"),
            fee_tier(fee),
            ZERO_SQRT_PRICE_LIMIT,
        )

        result = self.quoter.functions.quoteExactInputSingle(params).call()

        return int(result[0])

    @property
    def uses_deadline(self) -> bool:
        """True when the router struct carries a deadline field."""
        return self.dex in DEADLINE_DEXES

    def build_exact_input_single(
        self,
        token_in: str,
        token_out: str,
        fee: int,
        recipient: str,
        amount_in_raw: int,
        min_amount_out_raw: int,
        deadline: int | None = None,
    ) -> ContractFunction:
        """Return the ``exactInputSingle`` call for a rebalancing swap.

        ``deadline`` is encoded only for DEXes whose router requires it; when
        omitted, the swap stays valid for ``deadline_seconds`` from now.
        """
        token_in, token_out = token_pair(self.w3, token_in, token_out)
        fee = fee_tier(fee)
        recipient = self.w3.to_checksum_address(recipient)
        amount_in = positive_amount(amount_in_raw, "amount_in_raw")
        min_amount_out = positive_amount(
            min_amount_out_raw,
            "min_amount_out_raw",
        )

        if self.uses_deadline:
            params = (
                token_in,
                token_out,
                fee,
                recipient,
                self._deadline(deadline),
                amount_in,
                min_amount_out,
                ZERO_SQRT_PRICE_LIMIT,
            )
        elif deadline is not None:
            raise ValueError(f"{self.dex} router does not accept a deadline")
        else:
            params = (
                token_in,
                token_out,
                fee,
                recipient,
                amount_in,
                min_amount_out,
                ZERO_SQRT_PRICE_LIMIT,
            )

        return self.contract.functions.exactInputSingle(params)

    def _deadline(self, deadline: int | None) -> int:
        """Return an explicit deadline or ``now + deadline_seconds``."""
        if deadline is None:
            return int(time.time()) + self.deadline_seconds

        if (
            isinstance(deadline, bool)
            or not isinstance(deadline, int)
            or deadline <= 0
        ):
            raise ValueError("deadline must be a positive integer")

        return deadline
