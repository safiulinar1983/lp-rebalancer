from web3 import Web3
from decimal import Decimal

from config import load_config
from blockchain.pancake_v3 import PancakeV3Pool
from blockchain.position_manager import PositionManager
from blockchain.fees import calculate_fees_value_usd
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
    fee_threshold_usd=Decimal(str(config.fee_threshold_usd)),
)


pool_state = pool.read_state()

position = position_manager.find_position(
    token0=pool_state.token0,
    token1=pool_state.token1,
    fee=pool_state.fee,
)

token_id = position.token_id

# Simulate fee collection without sending a transaction.
amount0_raw, amount1_raw = position_manager.simulate_collect_fees(
    token_id
)

fees_value_usd = calculate_fees_value_usd(
    amount0_raw,
    amount1_raw,
    pool_state.token0_decimals,
    pool_state.token1_decimals,
    Decimal("1"),
    Decimal(str(pool_state.price)),
)

decision = strategy.evaluate(
    pool_state,
    position,
    fees_value_usd=fees_value_usd,
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
print(f"Liquidity:     {position.liquidity}")
print(f"Tokens owed 0: {position.tokens_owed0}")
print(f"Tokens owed 1: {position.tokens_owed1}")
print()
print(f"Fees value:    ${fees_value_usd:.6f}")
print(f"Decision:      {decision}")
print("=" * 50)
