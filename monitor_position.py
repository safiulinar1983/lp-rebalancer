from web3 import Web3

from config import load_config
from blockchain.pancake_v3 import PancakeV3Pool
from blockchain.position_manager import PositionManager
from strategy import Strategy


config = load_config()

w3 = Web3(Web3.HTTPProvider(config.rpc_url))

if not w3.is_connected():
    raise RuntimeError("Cannot connect to RPC")

if w3.eth.chain_id != config.expected_chain_id:
    raise RuntimeError(
        f"Wrong network: expected {config.expected_chain_id}, "
        f"got {w3.eth.chain_id}"
    )


pool = PancakeV3Pool(
    w3=w3,
    address=config.pool_address,
)

position_manager = PositionManager(
    w3=w3,
    address=config.position_manager_address,
    wallet=config.wallet_address,
)

strategy = Strategy(
    range_half_width=config.range_half_width,
)


pool_state = pool.read_state()

token_ids = position_manager.get_token_ids()

if not token_ids:
    raise RuntimeError("No LP positions found")

token_id = token_ids[0]
position = position_manager.read_position(token_id)

decision = strategy.evaluate(
    pool_state,
    position,
)


print("=" * 50)
print("LP POSITION MONITOR")
print("=" * 50)

print(f"Network:       {config.network}")
print(f"Pool:          {config.pool_address}")
print(f"Position NFT:  #{token_id}")
print()
print(f"Current tick:  {pool_state.tick}")
print(f"Tick lower:    {position.lower_tick}")
print(f"Tick upper:    {position.upper_tick}")
print()
print(f"Decision:      {decision}")
print("=" * 50)
