from web3 import Web3


RPC_URL = "https://mainnet.base.org"

WALLET_ADDRESS = Web3.to_checksum_address(
    "0x87e58e8B5983FC4fF8199d3E16264ad39182a96e"
)

POSITION_MANAGER = Web3.to_checksum_address(
    "0x46A15B0b27311cedF172AB29E4f4766fbE7F4364"
)

POOL_ADDRESS = Web3.to_checksum_address(
    "0x26e263efdc91f0d3279e2ec2bd58a7ca5c2fce62"
)

CB_BTC = Web3.to_checksum_address(
    "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf"
)

USDC = Web3.to_checksum_address(
    "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
)


POSITION_MANAGER_ABI = [
    {
        "inputs": [
            {
                "internalType": "uint256",
                "name": "tokenId",
                "type": "uint256",
            }
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
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "owner",
                "type": "address",
            }
        ],
        "name": "balanceOf",
        "outputs": [
            {
                "internalType": "uint256",
                "name": "",
                "type": "uint256",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "owner",
                "type": "address",
            },
            {
                "internalType": "uint256",
                "name": "index",
                "type": "uint256",
            },
        ],
        "name": "tokenOfOwnerByIndex",
        "outputs": [
            {
                "internalType": "uint256",
                "name": "",
                "type": "uint256",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    raise RuntimeError("Cannot connect to Base RPC")


manager = w3.eth.contract(
    address=POSITION_MANAGER,
    abi=POSITION_MANAGER_ABI,
)


def get_positions():

    count = manager.functions.balanceOf(
        WALLET_ADDRESS
    ).call()

    print()
    print("=" * 60)
    print("PancakeSwap V3 Positions")
    print("=" * 60)

    print(f"Wallet:     {WALLET_ADDRESS}")
    print(f"Positions:  {count}")
    print()

    found = 0

    for i in range(count):

        token_id = manager.functions.tokenOfOwnerByIndex(
            WALLET_ADDRESS,
            i,
        ).call()

        position = manager.functions.positions(
            token_id
        ).call()

        (
            nonce,
            operator,
            token0,
            token1,
            fee,
            tick_lower,
            tick_upper,
            liquidity,
            fee_growth_0,
            fee_growth_1,
            tokens_owed_0,
            tokens_owed_1,
        ) = position

        # We are interested only in our cbBTC/USDC 0.05% pool.
        if (
            Web3.to_checksum_address(token0) == USDC
            and Web3.to_checksum_address(token1) == CB_BTC
            and fee == 500
        ):
            found += 1

            print("-" * 60)
            print(f"Token ID:       {token_id}")
            print(f"Token0:         {token0}")
            print(f"Token1:         {token1}")
            print(f"Fee:            {fee / 10_000:.2f}%")
            print(f"Tick lower:     {tick_lower}")
            print(f"Tick upper:     {tick_upper}")
            print(f"Liquidity:      {liquidity}")
            print(f"Tokens owed 0:  {tokens_owed_0}")
            print(f"Tokens owed 1:  {tokens_owed_1}")
            print()

    print("-" * 60)

    if found == 0:
        print("No cbBTC/USDC 0.05% PancakeSwap V3 position found.")
    else:
        print(f"Found {found} matching position(s).")

    print("=" * 60)


if __name__ == "__main__":
    get_positions()
