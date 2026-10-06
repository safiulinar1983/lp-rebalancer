from decimal import Decimal
from dataclasses import dataclass
from web3 import Web3
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


POOL_ABI = [
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "fee",
        "outputs": [{"name": "", "type": "uint24"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "tickSpacing",
        "outputs": [{"name": "", "type": "int24"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "observationIndex", "type": "uint16"},
            {"name": "observationCardinality", "type": "uint16"},
            {"name": "observationCardinalityNext", "type": "uint16"},
            {"name": "feeProtocol", "type": "uint32"},
            {"name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

ERC20_ABI = [
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]


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
