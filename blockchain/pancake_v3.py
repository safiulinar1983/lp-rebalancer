from web3 import Web3


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

    def read_state(self) -> dict:
        slot0 = self.contract.functions.slot0().call()

        return {
            "address": self.address,
            "token0": self.contract.functions.token0().call(),
            "token1": self.contract.functions.token1().call(),
            "fee": self.contract.functions.fee().call(),
            "tick_spacing": self.contract.functions.tickSpacing().call(),
            "sqrt_price_x96": slot0[0],
            "tick": slot0[1],
            "liquidity": self.contract.functions.liquidity().call(),
        }
