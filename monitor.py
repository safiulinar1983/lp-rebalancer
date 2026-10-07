import time
from decimal import Decimal

from web3 import Web3

from config import load_config


# =========================
# Pool ABI
# =========================

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
]


# =========================
# Configuration
# =========================

config = load_config()

RPC_URL = config.rpc_url
POOL_ADDRESS = Web3.to_checksum_address(config.pool_address)


# =========================
# Web3
# =========================

w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    raise RuntimeError(f"Cannot connect to RPC: {RPC_URL}")

actual_chain_id = w3.eth.chain_id

if actual_chain_id != config.expected_chain_id:
    raise RuntimeError(
        f"Wrong network: expected chain_id={config.expected_chain_id}, "
        f"got {actual_chain_id}"
    )


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


def tick_to_price(tick, token0, token1):
    """
    Calculate token1 price in token0 using the V3 tick.

    This is a generic calculation based on token ordering.
    Token decimals are not known yet, so this returns the
    raw V3 ratio.
    """

    if token0.lower() < token1.lower():
        return Decimal("1.0001") ** Decimal(tick)

    return Decimal("1.0001") ** Decimal(-tick)


def print_pool_info():
    sqrt_price_x96, tick = get_pool_state()

    token0 = pool.functions.token0().call()
    token1 = pool.functions.token1().call()

    fee = pool.functions.fee().call()
    tick_spacing = pool.functions.tickSpacing().call()

    print()
    print("=" * 50)
    print("PancakeSwap V3 LP Monitor")
    print("=" * 50)
    print(f"Network:       {config.network}")
    print(f"Chain ID:      {actual_chain_id}")
    print(f"Pool:          {POOL_ADDRESS}")
    print(f"Token0:        {token0}")
    print(f"Token1:        {token1}")
    print(f"Fee:           {fee / 10_000:.2f}%")
    print(f"Tick spacing:  {tick_spacing}")
    print()
    print(f"sqrtPriceX96:  {sqrt_price_x96}")
    print(f"Current tick:  {tick}")
    print()
    print("Status:        MONITORING")
    print("=" * 50)


# =========================
# Main monitor
# =========================

def monitor():
    print("LP Monitor started")
    print(f"Connecting to PancakeSwap V3 on {config.network}...")

    while True:
        try:
            print_pool_info()

        except Exception as e:
            print(f"Monitor error: {e}")

        time.sleep(config.check_interval)


if __name__ == "__main__":
    monitor()
