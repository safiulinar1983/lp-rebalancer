import time
from decimal import Decimal

from web3 import Web3


# =========================
# Configuration
# =========================

RPC_URL = "https://mainnet.base.org"

POOL_ADDRESS = Web3.to_checksum_address(
    "0x26e263efdc91f0d3279e2ec2bd58a7ca5c2fce62"
)

CB_BTC_ADDRESS = Web3.to_checksum_address(
    "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf"
)

USDC_ADDRESS = Web3.to_checksum_address(
    "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
)


# PancakeSwap V3 Pool ABI
POOL_ABI = [
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
    {
        "inputs": [],
        "name": "token0",
        "outputs": [
            {"name": "", "type": "address"}
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [
            {"name": "", "type": "address"}
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "fee",
        "outputs": [
            {"name": "", "type": "uint24"}
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "tickSpacing",
        "outputs": [
            {"name": "", "type": "int24"}
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


# =========================
# Web3
# =========================

w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    raise RuntimeError("Cannot connect to Base RPC")


pool = w3.eth.contract(
    address=POOL_ADDRESS,
    abi=POOL_ABI,
)


# =========================
# Helpers
# =========================

def get_pool_state():
    slot0 = pool.functions.slot0().call()

    sqrt_price_x96 = slot0[0]
    tick = slot0[1]

    return sqrt_price_x96, tick


def tick_to_price(tick):
    """
    Convert V3 tick to USDC price per cbBTC.

    Pool:
        token0 = USDC  (6 decimals)
        token1 = cbBTC (8 decimals)

    V3 raw price is token1/token0.
    We invert it to get cbBTC/USDC.
    """

    raw_price = Decimal("1.0001") ** Decimal(tick)

    # Adjust for token decimals:
    # token0 = USDC 6 decimals
    # token1 = cbBTC 8 decimals
    price_token1_per_token0 = raw_price * (
        Decimal(10) ** (6 - 8)
    )

    # We need USDC per cbBTC
    return Decimal(1) / price_token1_per_token0


def print_pool_info():

    sqrt_price_x96, tick = get_pool_state()

    token0 = pool.functions.token0().call()
    token1 = pool.functions.token1().call()

    fee = pool.functions.fee().call()
    tick_spacing = pool.functions.tickSpacing().call()

    price = tick_to_price(tick)

    print()
    print("=" * 50)
    print("PancakeSwap V3 LP Monitor")
    print("=" * 50)

    print(f"Network:       Base")
    print(f"Pool:          {POOL_ADDRESS}")
    print(f"Token0:        {token0}")
    print(f"Token1:        {token1}")
    print(f"Fee:           {fee / 10_000:.2f}%")
    print(f"Tick spacing:  {tick_spacing}")
    print()
    print(f"sqrtPriceX96:  {sqrt_price_x96}")
    print(f"Current tick:  {tick}")
    print(f"Price cbBTC:   ${price:,.2f} USDC")
    print()
    print("Status:        MONITORING")
    print("=" * 50)


# =========================
# Main monitor
# =========================

def monitor():

    print("LP Monitor started")
    print("Connecting to PancakeSwap V3 on Base...")

    while True:

        try:
            print_pool_info()

        except Exception as e:
            print(f"Monitor error: {e}")

        time.sleep(5)


if __name__ == "__main__":
    monitor()
