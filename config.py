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

# Rebalance cycle execution modes: DRY_RUN only plans and simulates.
MODE_DRY_RUN = "DRY_RUN"
MODE_LIVE = "LIVE"
MODES = (MODE_DRY_RUN, MODE_LIVE)

# Default slippage tolerance for swaps and liquidity limits: 0.5%.
DEFAULT_SLIPPAGE_BPS = 50


@dataclass(frozen=True)
class AppConfig:
    rpc_url: str
    pool_address: str
    range_half_width: Decimal
    fee_threshold_usd: Decimal
    check_interval: int
    mode: str
    slippage_bps: int
    max_gas_cost_usd: Decimal | None
    burn_closed_position: bool
    expected_chain_id: int
    network: str
    dex: str
    position_manager_address: str
    position_token_id: int | None
    wallet_address: str
    weth_address: str
    swap_router_address: str
    quoter_address: str
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


def _to_int_in_range(
    value: object,
    name: str,
    minimum: int,
    maximum: int,
) -> int:
    """Convert a YAML scalar to an integer inside an inclusive range."""
    message = f"{name} must be an integer from {minimum} to {maximum}"

    if value is None or isinstance(value, bool):
        raise ValueError(message)

    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc

    if str(result) != str(value).strip():
        raise ValueError(message)

    if not minimum <= result <= maximum:
        raise ValueError(message)

    return result


def _to_bool(value: object, name: str) -> bool:
    """Convert a YAML scalar to ``bool`` without accepting truthy strings."""
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false")

    return value


def _optional_address(value: object, name: str) -> str:
    """Return an optional 0x-prefixed address; an empty value means unset."""
    text = str(value or "").strip()

    if not text:
        return ""

    if not text.startswith("0x") or len(text) != 42:
        raise ValueError(
            f"{name} must be a 0x-prefixed 42-character address"
        )

    return text


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

    mode = str(strategy_config.get("mode", MODE_DRY_RUN)).strip().upper()

    if mode not in MODES:
        raise ValueError(
            f"strategy.mode must be one of {', '.join(MODES)}"
        )

    slippage_bps = _to_int_in_range(
        strategy_config.get("slippage_bps", DEFAULT_SLIPPAGE_BPS),
        "strategy.slippage_bps",
        0,
        9_999,
    )

    raw_max_gas_cost_usd = strategy_config.get("max_gas_cost_usd")

    if raw_max_gas_cost_usd is None or (
        isinstance(raw_max_gas_cost_usd, str)
        and not raw_max_gas_cost_usd.strip()
    ):
        max_gas_cost_usd = None
    else:
        max_gas_cost_usd = _to_decimal(
            raw_max_gas_cost_usd,
            "strategy.max_gas_cost_usd",
        )

        if max_gas_cost_usd < 0:
            raise ValueError(
                "strategy.max_gas_cost_usd must be non-negative"
            )

    burn_closed_position = _to_bool(
        strategy_config.get("burn_closed_position", False),
        "strategy.burn_closed_position",
    )

    swap_router_address = _optional_address(
        (config.get("swap_router") or {}).get("address", ""),
        "swap_router.address",
    )

    quoter_address = _optional_address(
        (config.get("quoter") or {}).get("address", ""),
        "quoter.address",
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
        mode=mode,
        slippage_bps=slippage_bps,
        max_gas_cost_usd=max_gas_cost_usd,
        burn_closed_position=burn_closed_position,
        expected_chain_id=expected_chain_id,
        network=network,
        dex=str(config.get("dex", "pancakeswap_v3")).strip().lower(),
        position_manager_address=position_manager_address,
        position_token_id=position_token_id,
        wallet_address=wallet_address,
        weth_address=weth_address,
        swap_router_address=swap_router_address,
        quoter_address=quoter_address,
        token0_usd_feed=str(oracle_config.get("token0_usd_feed", "")).strip(),
        token1_usd_feed=str(oracle_config.get("token1_usd_feed", "")).strip(),
        oracle_max_age_seconds=_to_positive_int(
            oracle_config.get("max_age_seconds", 3600),
            "oracle.max_age_seconds",
        ),
    )
