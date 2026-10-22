"""Read-only monitor: classify the configured LP position and report it.

The monitor never signs or sends transactions. It stores a snapshot in the
local SQLite store and prints a human-readable report (CLI output is
intentionally print-based; ``main.py`` uses ``logging``).
"""

from decimal import Decimal

from web3 import Web3

from config import AppConfig, load_config
from blockchain.dex_manager import DEXManager
from blockchain.position_manager import PositionManager
from blockchain.fees import calculate_fees_value_usd
from blockchain.oracle import get_token_price_usd
from blockchain.rpc import connect
from pool_guard import read_pool_state
from strategy import Strategy
from storage.sqlite_store import SQLiteStore

# Tokens explicitly listed in ``oracle.stablecoins`` have no feed and are
# valued at exactly one dollar. Every other token needs a Chainlink feed.
STABLECOIN_PRICE_USD = Decimal("1")


def _oracle_price(w3: Web3, feed_address: str, max_age_seconds: int) -> Decimal:
    """Read a Chainlink feed, turning RPC failures into a clear error."""
    try:
        return get_token_price_usd(w3, feed_address, max_age_seconds)
    except Exception as exc:
        raise RuntimeError(
            f"Price unavailable for feed {feed_address}; stopping monitor: {exc}"
        ) from exc


def price_for_token(w3: Web3, config: AppConfig, token_address: str) -> Decimal:
    """Return the USD price of one pool token.

    Feeds are keyed by token address in ``oracle.feeds``, so the price does not
    depend on whether the token is ``token0`` or ``token1``: switching the pool
    does not require re-ordering the oracle settings. Tokens listed in
    ``oracle.stablecoins`` are valued at ``$1``; the pool spot price is never
    used as a substitute for a missing feed.
    """
    key = str(token_address).strip().lower()
    feed = config.oracle_feeds.get(key)

    if feed is not None:
        return _oracle_price(w3, feed.feed_address, feed.max_age_seconds)

    if key in config.oracle_stablecoins:
        return STABLECOIN_PRICE_USD

    raise RuntimeError(
        f"No oracle feed for token {token_address}: add it under "
        "oracle.feeds in config.yaml, or list it under oracle.stablecoins "
        "if it is a USD stablecoin"
    )


def resolve_token_prices(
    w3: Web3,
    config: AppConfig,
    token0: str,
    token1: str,
) -> tuple[Decimal, Decimal]:
    """Return ``(token0_usd, token1_usd)`` for the tokens of the pool."""
    return (
        price_for_token(w3, config, token0),
        price_for_token(w3, config, token1),
    )


def resolve_native_price_usd(w3: Web3, config: AppConfig) -> Decimal | None:
    """Return the native-token USD price used for gas, when it is configured.

    Gas is paid in native ETH, so its price is read from the feed of
    ``weth.address``. It does not depend on the pool containing WETH: a
    BTC/USDC pool can still value gas in USD.
    """
    feed = config.oracle_feeds.get(config.weth_address.lower())

    if feed is None:
        return None

    return _oracle_price(w3, feed.feed_address, feed.max_age_seconds)


def main() -> None:
    config = load_config()
    store = SQLiteStore()

    w3 = connect(config.rpc_url, expected_chain_id=config.expected_chain_id)

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
        fee_threshold_usd=config.fee_threshold_usd,
    )

    pool_state = read_pool_state(pool, config)
    token0_price_usd, token1_price_usd = resolve_token_prices(
        w3,
        config,
        pool_state.token0,
        pool_state.token1,
    )

    position = position_manager.find_position(
        token0=pool_state.token0,
        token1=pool_state.token1,
        fee=pool_state.fee,
        token_id=config.position_token_id,
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
        "decision": decision.action,
        "in_range": decision.in_range,
        "proposed_lower_tick": decision.proposed_lower_tick,
        "proposed_upper_tick": decision.proposed_upper_tick,
    }

    store.record_event("monitor_snapshot", snapshot)
    store.record_decision(decision.action, snapshot)

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
