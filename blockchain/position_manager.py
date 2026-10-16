"""Read-only access to the PancakeSwap V3 positions of the configured wallet."""

from web3 import Web3

from blockchain.abis import POSITION_MANAGER_ABI
from blockchain.positions import Position


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
        params = (
            token_id,
            liquidity,
            0,
            0,
            self.w3.eth.get_block("latest")["timestamp"] + 600,
        )

        return self.contract.functions.decreaseLiquidity(
            params
        ).call({
            "from": self.wallet,
        })

    def simulate_decrease_and_collect(
        self,
        token_id: int,
        liquidity: int,
    ) -> list[bytes]:
        decrease_params = (
            token_id,
            liquidity,
            0,
            0,
            self.w3.eth.get_block("latest")["timestamp"] + 600,
        )

        collect_params = (
            token_id,
            self.wallet,
            2**128 - 1,
            2**128 - 1,
        )

        decrease_data = (
            self.contract.functions.decreaseLiquidity(
                decrease_params
            )._encode_transaction_data()
        )

        collect_data = (
            self.contract.functions.collect(
                collect_params
            )._encode_transaction_data()
        )

        return self.contract.functions.multicall(
            [decrease_data, collect_data]
        ).call({
            "from": self.wallet,
        })

    def simulate_collect_fees(
        self,
        token_id: int,
    ) -> tuple[int, int]:
        collect_params = (
            token_id,
            self.wallet,
            2**128 - 1,
            2**128 - 1,
        )

        return self.contract.functions.collect(
            collect_params
        ).call({
            "from": self.wallet,
        })

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
