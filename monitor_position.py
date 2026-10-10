from decimal import Decimal

from web3 import Web3

from config import load_config
from blockchain.dex_manager import DEXManager
from blockchain.position_manager import PositionManager
from blockchain.fees import calculate_fees_value_usd
from blockchain.oracle import get_token_price_usd
from strategy import Strategy
from storage.sqlite_store import SQLiteStore


def main() -> None:
    config = load_config()
    store = SQLiteStore()

    w3 = Web3(Web3.HTTPProvider(config.rpc_url))

    if not w3.is_connected():
        raise RuntimeError("Cannot connect to RPC")

    if w3.eth.chain_id != config.expected_chain_id:
        raise RuntimeError(
            f"Wrong network: expected {config.expected_chain_id}, "
            f"got {w3.eth.chain_id}"
        )

    pool = DEXManager.create_pool(
        dex_name=config.dex,
        w3=w3,
        pool_address=config.pool_address,
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

    # Use configured Chainlink feeds independently.
    # For this test pool, an unconfigured token0 (USDC) is assumed to be $1.
    token0_feed = config.token0_usd_feed
    token1_feed = config.token1_usd_feed

    try:
        token0_price_usd = (
            get_token_price_usd(
                w3, token0_feed, config.oracle_max_age_seconds
            )
            if token0_feed
            else Decimal("1")
        )
        token1_price_usd = (
            get_token_price_usd(
                w3, token1_feed, config.oracle_max_age_seconds
            )
            if token1_feed
            else Decimal(str(pool_state.price))
        )
    except Exception as exc:
        raise RuntimeError(
            f"Price unavailable; stopping monitor: {exc}"
        ) from exc

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
        token0_price_usd,
        token1_price_usd,
    )

    decision = strategy.evaluate(
        pool_state,
        position,
        fees_value_usd=fees_value_usd,
    )

    snapshot = {
        "network": config.network,
        "pool_address": config.pool_address,
        "token_id": token_id,
        "current_tick": pool_state.tick,
        "lower_tick": position.lower_tick,
        "upper_tick": position.upper_tick,
        "liquidity": str(position.liquidity),
        "tokens_owed0": str(position.tokens_owed0),
        "tokens_owed1": str(position.tokens_owed1),
        "fees_value_usd": str(fees_value_usd),
        "decision": str(decision),
    }

    store.record_event("monitor_snapshot", snapshot)
    store.record_decision(str(decision), snapshot)

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


if __name__ == "__main__":
    main()
