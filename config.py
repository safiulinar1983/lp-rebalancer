"""Application configuration loaded from ``config.yaml``.

Strategy numbers are returned as ``Decimal`` so that no binary floating point
value ever reaches the price or balance math.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

# Repository-root config file; used when no explicit path is passed.
CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

# Base mainnet and Base Sepolia share this WETH predeploy address.
DEFAULT_WETH_ADDRESS = "0x4200000000000000000000000000000000000006"


@dataclass(frozen=True)
class AppConfig:
    rpc_url: str
    pool_address: str
    range_half_width: Decimal
    fee_threshold_usd: Decimal
    check_interval: int
    expected_chain_id: int
    network: str
    dex: str
    position_manager_address: str
    position_token_id: int | None
    wallet_address: str
    weth_address: str
    token0_usd_feed: str
    token1_usd_feed: str
    oracle_max_age_seconds: int


def _to_decimal(value: object, name: str) -> Decimal:
    """Convert a YAML scalar to ``Decimal`` without using binary floats."""
    if value is None or isinstance(value, bool):
        raise ValueError(f"{name} must be a number")

    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc

    if not result.is_finite():
        raise ValueError(f"{name} must be a finite number")

    return result


def _to_positive_int(value: object, name: str) -> int:
    """Convert a YAML scalar to a strictly positive integer."""
    if value is None or isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")

    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc

    if result <= 0 or str(result) != str(value).strip():
        raise ValueError(f"{name} must be a positive integer")

    return result


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load and validate the application configuration.

    ``path`` defaults to ``config.yaml`` next to this module, so the CLI tools
    work from any working directory.
    """
    config_path = Path(path) if path is not None else CONFIG_PATH

    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    network = config["network"]
    networks = config["networks"]

    if network not in networks:
        raise ValueError(f"Unknown network: {network}")

    network_config = networks[network]

    rpc_url = str(network_config["rpc_url"]).strip()
    expected_chain_id = int(network_config["chain_id"])

    if not rpc_url:
        raise ValueError("RPC URL is empty")

    pool_address = str(config["pool"]["address"]).strip()

    if not pool_address:
        raise ValueError("Pool address is empty")

    position_manager_address = str(config["position_manager"]["address"]).strip()
    wallet_address = str(config["wallet"]["address"]).strip()

    if not position_manager_address:
        raise ValueError("Position manager address is empty")

    if not wallet_address:
        raise ValueError("Wallet address is empty")

    raw_token_id = config["position_manager"].get("token_id")
    if raw_token_id is None:
        position_token_id = None
    else:
        position_token_id = _to_positive_int(
            raw_token_id,
            "position_manager.token_id",
        )

    strategy_config = config["strategy"]

    range_half_width = _to_decimal(
        strategy_config["range_half_width"],
        "strategy.range_half_width",
    )

    if range_half_width <= 0:
        raise ValueError("strategy.range_half_width must be positive")

    fee_threshold_usd = _to_decimal(
        strategy_config["fee_threshold_usd"],
        "strategy.fee_threshold_usd",
    )

    if fee_threshold_usd < 0:
        raise ValueError("strategy.fee_threshold_usd must be non-negative")

    check_interval = _to_positive_int(
        strategy_config["check_interval"],
        "strategy.check_interval",
    )

    oracle_config = config.get("oracle") or {}
    weth_config = config.get("weth") or {}

    weth_address = str(weth_config.get("address", DEFAULT_WETH_ADDRESS)).strip()

    if not weth_address:
        raise ValueError("weth.address is empty")

    return AppConfig(
        rpc_url=rpc_url,
        pool_address=pool_address,
        range_half_width=range_half_width,
        fee_threshold_usd=fee_threshold_usd,
        check_interval=check_interval,
        expected_chain_id=expected_chain_id,
        network=network,
        dex=str(config.get("dex", "pancakeswap_v3")).strip().lower(),
        position_manager_address=position_manager_address,
        position_token_id=position_token_id,
        wallet_address=wallet_address,
        weth_address=weth_address,
        token0_usd_feed=str(oracle_config.get("token0_usd_feed", "")).strip(),
        token1_usd_feed=str(oracle_config.get("token1_usd_feed", "")).strip(),
        oracle_max_age_seconds=_to_positive_int(
            oracle_config.get("max_age_seconds", 3600),
            "oracle.max_age_seconds",
        ),
    )
