import os

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

WETH = Web3.to_checksum_address(
    "0x4200000000000000000000000000000000000006"
)

POSITION_MANAGER = Web3.to_checksum_address(
    "0x27F971cb582BF9E50F397e4d29a5C7A34f11faA2"
)

ERC20_ABI = [
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

weth = w3.eth.contract(
    address=WETH,
    abi=ERC20_ABI,
)

amount = 100_000_000_000_000 # 0.0001 WETH

nonce = w3.eth.get_transaction_count(account.address)

tx = weth.functions.approve(
    POSITION_MANAGER,
    amount,
).build_transaction(
    {
        "from": account.address,
        "nonce": nonce,
        "chainId": w3.eth.chain_id,
        "gas": 100000,
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
