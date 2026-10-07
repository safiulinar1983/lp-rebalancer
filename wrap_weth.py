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

private_key = os.environ["PRIVATE_KEY"]
account = w3.eth.account.from_key(private_key)

WETH = Web3.to_checksum_address(
    "0x4200000000000000000000000000000000000006"
)

WETH_ABI = [
    {
        "inputs": [],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    }
]

weth = w3.eth.contract(
    address=WETH,
    abi=WETH_ABI,
)

amount = w3.to_wei(0.0001, "ether")

nonce = w3.eth.get_transaction_count(account.address)

tx = weth.functions.deposit().build_transaction(
    {
        "from": account.address,
        "value": amount,
        "nonce": nonce,
        "chainId": w3.eth.chain_id,
        "gas": 100000,
        "gasPrice": w3.eth.gas_price,
    }
)

signed = account.sign_transaction(tx)

tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

print("Transaction:", tx_hash.hex())
print("Waiting for confirmation...")

receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

print("Status:", receipt.status)
print("Block:", receipt.blockNumber)
