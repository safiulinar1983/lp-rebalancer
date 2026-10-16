"""PancakeSwap V3 position reads together with calldata builders.

Reading (``positions``, ``ownerOf``) never changes state. The ``build_*`` and
``simulate_*`` helpers prepare and dry-run the calls a rebalance cycle needs;
sending them is the job of ``blockchain.tx``.
"""

from web3 import Web3
from web3.contract.contract import ContractFunction

from blockchain.abis import POSITION_MANAGER_ABI
from blockchain.call_params import (
    fee_tier,
    non_negative_amount,
    token_pair,
    token_id as validate_token_id,
)
from blockchain.positions import Position

# Deadline attached to every prepared call, counted from the current block.
DEADLINE_SECONDS = 600

MAX_UINT128 = 2**128 - 1


class PositionManager:
    def __init__(self, w3: Web3, address: str, wallet: str):
        self.w3 = w3
        self.address = w3.to_checksum_address(address)
        self.wallet = w3.to_checksum_address(wallet)

        self.contract = w3.eth.contract(
            address=self.address,
            abi=POSITION_MANAGER_ABI,
        )

    def get_token_ids(self) -> list[int]:
        balance = self.contract.functions.balanceOf(
            self.wallet
        ).call()

        return [
            self.contract.functions.tokenOfOwnerByIndex(
                self.wallet,
                index,
            ).call()
            for index in range(balance)
        ]

    def find_position(
        self,
        token0: str,
        token1: str,
        fee: int,
        token_id: int | None = None,
    ) -> Position:
        token0 = self.w3.to_checksum_address(token0)
        token1 = self.w3.to_checksum_address(token1)

        if token_id is not None:
            if isinstance(token_id, bool) or not isinstance(token_id, int):
                raise ValueError("token_id must be a positive integer")
            if token_id <= 0:
                raise ValueError("token_id must be a positive integer")

            owner = self.contract.functions.ownerOf(token_id).call()
            owner = self.w3.to_checksum_address(owner)

            if owner != self.wallet:
                raise RuntimeError(
                    f"LP NFT #{token_id} is owned by {owner}, "
                    f"not configured wallet {self.wallet}"
                )

            position = self.read_position(token_id)
            actual_token0 = self.w3.to_checksum_address(position.token0)
            actual_token1 = self.w3.to_checksum_address(position.token1)

            if (
                actual_token0 != token0
                or actual_token1 != token1
                or position.fee != fee
            ):
                raise RuntimeError(
                    f"LP NFT #{token_id} does not match the configured pool: "
                    f"expected {token0}/{token1} fee={fee}, "
                    f"got {actual_token0}/{actual_token1} "
                    f"fee={position.fee}"
                )

            return position

        for candidate_id in self.get_token_ids():
            position = self.read_position(candidate_id)
            actual_token0 = self.w3.to_checksum_address(position.token0)
            actual_token1 = self.w3.to_checksum_address(position.token1)

            if (
                actual_token0 == token0
                and actual_token1 == token1
                and position.fee == fee
            ):
                return position

        raise RuntimeError(
            f"No LP position found for {token0}/{token1} fee={fee}"
        )

    def simulate_decrease_liquidity(
        self,
        token_id: int,
        liquidity: int,
    ) -> tuple[int, int]:
        return self.contract.functions.decreaseLiquidity(
            self._decrease_params(token_id, liquidity)
        ).call({
            "from": self.wallet,
        })

    def simulate_decrease_and_collect(
        self,
        token_id: int,
        liquidity: int,
    ) -> list[bytes]:
        """Dry-run closing a position: decrease everything and collect."""
        return self.build_close_position(
            token_id, liquidity
        ).call({
            "from": self.wallet,
        })

    def simulate_collect_fees(
        self,
        token_id: int,
    ) -> tuple[int, int]:
        return self.build_collect(token_id).call({
            "from": self.wallet,
        })

    def build_collect(self, token_id: int) -> ContractFunction:
        """Return the ``collect`` call that sweeps owed tokens to the wallet."""
        return self.contract.functions.collect(
            self._collect_params(token_id)
        )

    def build_increase_liquidity(
        self,
        token_id: int,
        amount0_desired: int,
        amount1_desired: int,
        amount0_min: int,
        amount1_min: int,
    ) -> ContractFunction:
        """Return the ``increaseLiquidity`` call used to compound fees.

        The tokens stay in the same NFT: this is how collected fees are put
        back to work without closing the position.
        """
        amount0_desired = non_negative_amount(
            amount0_desired,
            "amount0_desired",
        )
        amount1_desired = non_negative_amount(
            amount1_desired,
            "amount1_desired",
        )
        amount0_min = non_negative_amount(amount0_min, "amount0_min")
        amount1_min = non_negative_amount(amount1_min, "amount1_min")

        if amount0_desired == 0 and amount1_desired == 0:
            raise ValueError("At least one desired amount must be positive")

        if amount0_min > amount0_desired or amount1_min > amount1_desired:
            raise ValueError(
                "Minimum amounts cannot exceed the desired amounts"
            )

        params = (
            validate_token_id(token_id),
            amount0_desired,
            amount1_desired,
            amount0_min,
            amount1_min,
            self._deadline(),
        )

        return self.contract.functions.increaseLiquidity(params)

    def build_decrease_liquidity(
        self,
        token_id: int,
        liquidity: int,
        amount0_min: int = 0,
        amount1_min: int = 0,
    ) -> ContractFunction:
        """Return the ``decreaseLiquidity`` call for ``liquidity`` units."""
        return self.contract.functions.decreaseLiquidity(
            self._decrease_params(
                token_id,
                liquidity,
                amount0_min,
                amount1_min,
            )
        )

    def build_close_position(
        self,
        token_id: int,
        liquidity: int,
    ) -> ContractFunction:
        """Return the ``decreaseLiquidity`` + ``collect`` multicall.

        ``collect`` must follow every decrease: tokens of a decreased position
        only leave the contract when they are collected. The NFT is left with
        zero liquidity and can then either be kept or burned.
        """
        decrease_data = self.build_decrease_liquidity(
            token_id,
            liquidity,
        )._encode_transaction_data()

        collect_data = self.build_collect(
            token_id
        )._encode_transaction_data()

        return self.contract.functions.multicall(
            [decrease_data, collect_data]
        )

    def build_burn(self, token_id: int) -> ContractFunction:
        """Return the ``burn`` call that deletes an emptied LP NFT.

        The contract only accepts it when the position has no liquidity left
        and nothing left to collect.
        """
        return self.contract.functions.burn(validate_token_id(token_id))

    def simulate_increase_liquidity(
        self,
        token_id: int,
        amount0_desired: int,
        amount1_desired: int,
        amount0_min: int,
        amount1_min: int,
    ) -> tuple[int, int, int]:
        """Dry-run ``increaseLiquidity`` and return (liquidity, amount0, amount1)."""
        result = self.build_increase_liquidity(
            token_id,
            amount0_desired,
            amount1_desired,
            amount0_min,
            amount1_min,
        ).call({
            "from": self.wallet,
        })

        return int(result[0]), int(result[1]), int(result[2])

    def simulate_burn(self, token_id: int) -> None:
        """Dry-run ``burn`` through ``eth_call``."""
        self.build_burn(token_id).call({
            "from": self.wallet,
        })

    def _deadline(self) -> int:
        """Return a deadline timestamp relative to the latest block."""
        return (
            int(self.w3.eth.get_block("latest")["timestamp"])
            + DEADLINE_SECONDS
        )

    def _collect_params(self, token_id: int) -> tuple[int, str, int, int]:
        """Collect everything owed, straight to the wallet."""
        return (
            validate_token_id(token_id),
            self.wallet,
            MAX_UINT128,
            MAX_UINT128,
        )

    def _decrease_params(
        self,
        token_id: int,
        liquidity: int,
        amount0_min: int = 0,
        amount1_min: int = 0,
    ) -> tuple[int, int, int, int, int]:
        liquidity = non_negative_amount(liquidity, "liquidity")

        if liquidity == 0:
            raise ValueError("liquidity must be positive")

        return (
            validate_token_id(token_id),
            liquidity,
            non_negative_amount(amount0_min, "amount0_min"),
            non_negative_amount(amount1_min, "amount1_min"),
            self._deadline(),
        )

    def build_mint(
        self,
        *,
        token0: str,
        token1: str,
        fee: int,
        tick_lower: int,
        tick_upper: int,
        amount0_desired: int,
        amount1_desired: int,
        amount0_min: int,
        amount1_min: int,
        recipient: str | None = None,
    ) -> ContractFunction:
        """Return the ``mint`` call that opens a new LP position.

        Only values that could never be valid are rejected here; the tick
        spacing and the range limits are enforced by the pool and by the
        position manager contract itself.
        """
        token0, token1 = token_pair(self.w3, token0, token1)
        fee = fee_tier(fee)

        for name, tick in (("tick_lower", tick_lower), ("tick_upper", tick_upper)):
            if isinstance(tick, bool) or not isinstance(tick, int):
                raise ValueError(f"{name} must be an integer")

        if tick_lower >= tick_upper:
            raise ValueError("tick_lower must be smaller than tick_upper")

        amount0_desired = non_negative_amount(
            amount0_desired,
            "amount0_desired",
        )
        amount1_desired = non_negative_amount(
            amount1_desired,
            "amount1_desired",
        )
        amount0_min = non_negative_amount(amount0_min, "amount0_min")
        amount1_min = non_negative_amount(amount1_min, "amount1_min")

        if amount0_desired == 0 and amount1_desired == 0:
            raise ValueError("At least one desired amount must be positive")

        if amount0_min > amount0_desired or amount1_min > amount1_desired:
            raise ValueError(
                "Minimum amounts cannot exceed the desired amounts"
            )

        owner = (
            self.wallet
            if recipient is None
            else self.w3.to_checksum_address(recipient)
        )

        params = (
            token0,
            token1,
            fee,
            tick_lower,
            tick_upper,
            amount0_desired,
            amount1_desired,
            amount0_min,
            amount1_min,
            owner,
            self._deadline(),
        )

        return self.contract.functions.mint(params)

    def simulate_mint(
        self,
        *,
        token0: str,
        token1: str,
        fee: int,
        tick_lower: int,
        tick_upper: int,
        amount0_desired: int,
        amount1_desired: int,
        amount0_min: int,
        amount1_min: int,
        recipient: str | None = None,
    ) -> tuple[int, int, int, int]:
        """Dry-run a mint and return (token_id, liquidity, amount0, amount1)."""
        result = self.build_mint(
            token0=token0,
            token1=token1,
            fee=fee,
            tick_lower=tick_lower,
            tick_upper=tick_upper,
            amount0_desired=amount0_desired,
            amount1_desired=amount1_desired,
            amount0_min=amount0_min,
            amount1_min=amount1_min,
            recipient=recipient,
        ).call({
            "from": self.wallet,
        })

        return (
            int(result[0]),
            int(result[1]),
            int(result[2]),
            int(result[3]),
        )

    def read_position(self, token_id: int) -> Position:
        data = self.contract.functions.positions(
            token_id
        ).call()

        return Position(
            token_id=token_id,
            token0=data[2],
            token1=data[3],
            fee=data[4],
            lower_tick=data[5],
            upper_tick=data[6],
            liquidity=data[7],
            tokens_owed0=data[10],
            tokens_owed1=data[11],
        )
