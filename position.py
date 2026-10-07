from web3 import Web3

from config import load_config


POSITION_MANAGER_ABI = [
    {
        "inputs": [],
        "name": "nextId",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"},
        ],
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
        "inputs": [
            {"name": "tokenId", "type": "uint256"},
        ],
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


config = load_config()

w3 = Web3(Web3.HTTPProvider(config.rpc_url))

if not w3.is_connected():
    raise RuntimeError(f"Cannot connect to RPC: {config.rpc_url}")

actual_chain_id = w3.eth.chain_id

if actual_chain_id != config.expected_chain_id:
    raise RuntimeError(
        f"Wrong network: expected {config.expected_chain_id}, "
        f"got {actual_chain_id}"
    )

POSITION_MANAGER = Web3.to_checksum_address(
    config.position_manager_address
)
WALLET = Web3.to_checksum_address(
    config.wallet_address
)

position_manager = w3.eth.contract(
    address=POSITION_MANAGER,
    abi=POSITION_MANAGER_ABI,
)


def inspect_positions():
    balance = position_manager.functions.balanceOf(WALLET).call()

    print()
    print("=" * 50)
    print("PancakeSwap V3 LP Positions")
    print("=" * 50)
    print(f"Network:          {config.network}")
    print(f"Chain ID:         {actual_chain_id}")
    print(f"Wallet:           {WALLET}")
    print(f"Position manager:  {POSITION_MANAGER}")
    print(f"NFT positions:    {balance}")
    print()

    if balance == 0:
        print("No LP positions found.")
        print("=" * 50)
        return

    for index in range(balance):
        token_id = position_manager.functions.tokenOfOwnerByIndex(
            WALLET,
            index,
        ).call()

        position = position_manager.functions.positions(token_id).call()

        (
            nonce,
            operator,
            token0,
            token1,
            fee,
            tick_lower,
            tick_upper,
            liquidity,
            fee_growth_inside0,
            fee_growth_inside1,
            tokens_owed0,
            tokens_owed1,
        ) = position

        print(f"Token ID:       {token_id}")
        print(f"Token0:         {token0}")
        print(f"Token1:         {token1}")
        print(f"Fee:            {fee}")
        print(f"Tick lower:     {tick_lower}")
        print(f"Tick upper:     {tick_upper}")
        print(f"Liquidity:      {liquidity}")
        print(f"Tokens owed 0:  {tokens_owed0}")
        print(f"Tokens owed 1:  {tokens_owed1}")
        print("-" * 50)

    print("=" * 50)


if __name__ == "__main__":
    inspect_positions()
