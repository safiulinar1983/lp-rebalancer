from dataclasses import dataclass
from decimal import Decimal

from web3 import Web3

from blockchain.abis import ERC20_ABI, POOL_ABI
from blockchain.price import price_token1_in_token0


@dataclass(frozen=True)
class PoolState:
    address: str
    token0: str
    token1: str
    token0_decimals: int
    token1_decimals: int
    fee: int
    tick_spacing: int
    sqrt_price_x96: int
    tick: int
    liquidity: int
    price: Decimal


class PancakeV3Pool:
    def __init__(self, w3: Web3, address: str):
        self.w3 = w3
        self.address = w3.to_checksum_address(address)

        self.contract = w3.eth.contract(
            address=self.address,
            abi=POOL_ABI,
        )

    def token_decimals(self) -> tuple[int, int]:
        token0 = self.w3.eth.contract(
            address=self.contract.functions.token0().call(),
            abi=ERC20_ABI,
        )
        token1 = self.w3.eth.contract(
            address=self.contract.functions.token1().call(),
            abi=ERC20_ABI,
        )

        return (
            token0.functions.decimals().call(),
            token1.functions.decimals().call(),
        )

    def read_state(self) -> PoolState:
        slot0 = self.contract.functions.slot0().call()
        token0_decimals, token1_decimals = self.token_decimals()

        price = price_token1_in_token0(
            slot0[0],
            token0_decimals,
            token1_decimals,
        )

        return PoolState(
            address=self.address,
            token0=self.contract.functions.token0().call(),
            token1=self.contract.functions.token1().call(),
            token0_decimals=token0_decimals,
            token1_decimals=token1_decimals,
            fee=self.contract.functions.fee().call(),
            tick_spacing=self.contract.functions.tickSpacing().call(),
            sqrt_price_x96=slot0[0],
            tick=slot0[1],
            liquidity=self.contract.functions.liquidity().call(),
            price=price,
        )
