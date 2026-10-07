from web3 import Web3

from strategy import Position


POSITION_MANAGER_ABI = [
    {
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "index", "type": "uint256"},
        ],
        "name": "tokenOfOwnerByIndex",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "positions",
        "outputs": [
            {"name": "nonce", "type": "uint96"},
            {"name": "operator", "type": "address"},
            {"name": "token0", "type": "address"},
            {"name": "token1", "type": "address"},
            {"name": "fee", "type": "uint24"},
            {"name": "tickLower", "type": "int24"},
            {"name": "tickUpper", "type": "int24"},
            {"name": "liquidity", "type": "uint128"},
            {"name": "feeGrowthInside0LastX128", "type": "uint256"},
            {"name": "feeGrowthInside1LastX128", "type": "uint256"},
            {"name": "tokensOwed0", "type": "uint128"},
            {"name": "tokensOwed1", "type": "uint128"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


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

    def read_position(self, token_id: int) -> Position:
        data = self.contract.functions.positions(
            token_id
        ).call()

        return Position(
            lower_tick=data[5],
            upper_tick=data[6],
        )
