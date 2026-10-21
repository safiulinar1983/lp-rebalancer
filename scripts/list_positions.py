"""List the V3 LP positions owned by the configured wallet.

Read-only: uses ``PositionManager`` and the shared ABI constants::

    python scripts/list_positions.py
"""

import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python scripts/list_positions.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blockchain.position_manager import PositionManager
from blockchain.rpc import connect
from config import AppConfig, load_config
from scripts._common import dex_title


def print_positions(
    manager: PositionManager,
    config: AppConfig,
    chain_id: int,
) -> None:
    """Print every NFT position owned by the configured wallet."""
    token_ids = manager.get_token_ids()

    print()
    print("=" * 50)
    print(f"{dex_title(config.dex)} LP Positions")
    print("=" * 50)
    print(f"Network:           {config.network}")
    print(f"Chain ID:          {chain_id}")
    print(f"Wallet:            {manager.wallet}")
    print(f"Position manager:  {manager.address}")
    print(f"NFT positions:     {len(token_ids)}")
    print()

    if not token_ids:
        print("No LP positions found.")
        print("=" * 50)
        return

    for token_id in token_ids:
        position = manager.read_position(token_id)

        print(f"Token ID:       {position.token_id}")
        print(f"Token0:         {position.token0}")
        print(f"Token1:         {position.token1}")
        print(f"Fee:            {position.fee}")
        print(f"Tick lower:     {position.lower_tick}")
        print(f"Tick upper:     {position.upper_tick}")
        print(f"Liquidity:      {position.liquidity}")
        print(f"Tokens owed 0:  {position.tokens_owed0}")
        print(f"Tokens owed 1:  {position.tokens_owed1}")
        print("-" * 50)

    print("=" * 50)


def main() -> None:
    config = load_config()
    w3 = connect(config.rpc_url, expected_chain_id=config.expected_chain_id)

    manager = PositionManager(
        w3=w3,
        address=config.position_manager_address,
        wallet=config.wallet_address,
    )

    print_positions(manager, config, int(w3.eth.chain_id))


if __name__ == "__main__":
    main()
