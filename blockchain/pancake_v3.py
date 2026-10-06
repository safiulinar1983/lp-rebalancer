from web3 import Web3
from dataclasses import dataclass
from blockchain.price import price_token1_in_token0

@dataclass(frozen=True)
class PoolState:
    address: str
    token0: str
    token1: str
    fee: int
    tick_spacing: int
    sqrt_price_x96: int
    tick: int
    liquidity: int
    price: object


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


class PancakeV3Pool:
    def __init__(self, w3: Web3, address: str):
        self.w3 = w3
        self.address = w3.to_checksum_address(address)

        self.contract = w3.eth.contract(
            address=self.address,
            abi=POOL_ABI,
        )

    def read_state(self) -> PoolState:
        slot0 = self.contract.functions.slot0().call()
        price = price_token1_in_token0(
            slot0[0],
            6,
            8,
        )

        return PoolState(
            address=self.address,
            token0=self.contract.functions.token0().call(),
            token1=self.contract.functions.token1().call(),
            fee=self.contract.functions.fee().call(),
            tick_spacing=self.contract.functions.tickSpacing().call(),
            sqrt_price_x96=slot0[0],
            tick=slot0[1],
            liquidity=self.contract.functions.liquidity().call(),
            price=price,
        )
