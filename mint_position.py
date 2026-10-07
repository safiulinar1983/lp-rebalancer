import os
from decimal import Decimal

from dotenv import load_dotenv
from web3 import Web3

from config import load_config


load_dotenv()

config = load_config()

w3 = Web3(Web3.HTTPProvider(config.rpc_url))

if not w3.is_connected():
    raise RuntimeError("Cannot connect to RPC")

if w3.eth.chain_id != config.expected_chain_id:
    raise RuntimeError("Wrong network")

account = w3.eth.account.from_key(os.environ["PRIVATE_KEY"])

POSITION_MANAGER = Web3.to_checksum_address(
    "0x27F971cb582BF9E50F397e4d29a5C7A34f11faA2"
)

POOL = Web3.to_checksum_address(
    config.pool_address
)

POSITION_MANAGER_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "token0", "type": "address"},
                    {"name": "token1", "type": "address"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "tickLower", "type": "int24"},
                    {"name": "tickUpper", "type": "int24"},
                    {"name": "amount0Desired", "type": "uint256"},
                    {"name": "amount1Desired", "type": "uint256"},
                    {"name": "amount0Min", "type": "uint256"},
                    {"name": "amount1Min", "type": "uint256"},
                    {"name": "recipient", "type": "address"},
                    {"name": "deadline", "type": "uint256"},
                ],
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "mint",
        "outputs": [
            {"name": "tokenId", "type": "uint256"},
            {"name": "liquidity", "type": "uint128"},
            {"name": "amount0", "type": "uint256"},
            {"name": "amount1", "type": "uint256"},
        ],
        "stateMutability": "payable",
        "type": "function",
    }
]

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

pool = w3.eth.contract(
    address=POOL,
    abi=POOL_ABI,
)

position_manager = w3.eth.contract(
    address=POSITION_MANAGER,
    abi=POSITION_MANAGER_ABI,
)


token0 = Web3.to_checksum_address(
    pool.functions.token0().call()
)

token1 = Web3.to_checksum_address(
    pool.functions.token1().call()
)

fee = pool.functions.fee().call()

slot0 = pool.functions.slot0().call()
current_tick = slot0[1]

tick_spacing = 10

tick_lower = 219000
tick_upper = 219200

amount0_desired = 1_000_000
amount1_desired = 100_000_000_000_000

deadline = w3.eth.get_block("latest")["timestamp"] + 600

params = (
    token0,
    token1,
    fee,
    tick_lower,
    tick_upper,
    amount0_desired,
    amount1_desired,
    0,
    0,
    account.address,
    deadline,
)

print("=" * 50)
print("LP MINT SIMULATION")
print("=" * 50)
print("Wallet:       ", account.address)
print("Pool:         ", POOL)
print("Token0:       ", token0)
print("Token1:       ", token1)
print("Fee:          ", fee)
print("Current tick: ", current_tick)
print("Tick lower:   ", tick_lower)
print("Tick upper:   ", tick_upper)
print("Amount0:      ", amount0_desired)
print("Amount1:      ", amount1_desired)
print("=" * 50)

nonce = w3.eth.get_transaction_count(account.address)

tx = position_manager.functions.mint(params).build_transaction(
    {
        "from": account.address,
        "value": 0,
        "nonce": nonce,
        "chainId": w3.eth.chain_id,
        "gas": 500000,
        "gasPrice": w3.eth.gas_price,
    }
)

signed = account.sign_transaction(tx)

tx_hash = w3.eth.send_raw_transaction(
    signed.raw_transaction
)

print("Transaction:", tx_hash.hex())
print("Waiting for confirmation...")

receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

print("Status:", receipt.status)
print("Block:", receipt.blockNumber)
