"""Application configuration loaded from ``config.yaml``.

Strategy numbers are returned as ``Decimal`` so that no binary floating point
value ever reaches the price or balance math.

Network profiles live under ``networks`` and are keyed by chain id; the
top-level ``network`` value selects one of them and ``connect`` verifies the
RPC chain id at runtime. Per-network settings include the RPC endpoint, WETH,
oracle feeds and the ``dexes`` map. The ``dex`` key selects one DEX profile,
which is resolved into the flat ``AppConfig`` fields used by the rest of the
application.

RPC URLs may reference environment variables, e.g.
``${BASE_RPC_URL:-https://sepolia.base.org}``; ``.env`` next to the config
file is loaded before expansion.
"""

import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Repository-root config file; used when no explicit path is passed.
CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

# Base mainnet and Base Sepolia share this WETH predeploy address.
DEFAULT_WETH_ADDRESS = "0x4200000000000000000000000000000000000006"

# Rebalance cycle execution modes: DRY_RUN only plans and simulates.
MODE_DRY_RUN = "DRY_RUN"
MODE_LIVE = "LIVE"
MODES = (MODE_DRY_RUN, MODE_LIVE)

# DEX adapters supported by the pool and swap-router layers.
DEFAULT_DEX = "pancakeswap_v3"
SUPPORTED_DEXES = ("uniswap_v3", "pancakeswap_v3")

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


def _required_address(value: object, name: str) -> str:
    """Return a required 0x-prefixed address; an empty value is an error."""
    address = _optional_address(value, name)

    if not address:
        raise ValueError(f"{name} is empty")

    return address


def _mapping(value: object, name: str) -> dict:
    """Return a YAML mapping, treating a missing value as an empty one."""
    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")

    return value


_ENV_REFERENCE = re.compile(
    r"^\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}$"
)


def _resolve_env(value: object) -> str:
    """Expand a ``${NAME}`` or ``${NAME:-default}`` reference from the env."""
    text = str(value or "").strip()
    match = _ENV_REFERENCE.fullmatch(text)

    if match is None:
        return text

    name, default = match.groups()
    return os.environ.get(name, "").strip() or (default or "").strip()


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load and validate the application configuration.

    ``path`` defaults to ``config.yaml`` next to this module, so the CLI tools
    work from any working directory.
    """
    config_path = Path(path) if path is not None else CONFIG_PATH
    load_dotenv(config_path.parent / ".env")

    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    networks = config.get("networks")

    if not isinstance(networks, dict):
        raise ValueError("networks must map chain ids to network settings")

    raw_chain_id = config.get("network")

    if raw_chain_id is None:
        raise ValueError("network (chain id) is required")

    try:
        expected_chain_id = int(raw_chain_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"network must be a chain id, got {raw_chain_id!r}"
        ) from exc

    network_config = networks.get(expected_chain_id)

    if network_config is None:
        network_config = networks.get(str(expected_chain_id))

    if not isinstance(network_config, dict):
        raise ValueError(f"Unknown chain_id: {expected_chain_id}")

    network = str(
        network_config.get("name") or expected_chain_id
    ).strip()

    rpc_url = _resolve_env(network_config.get("rpc_url", ""))

    if not rpc_url:
        raise ValueError(
            f"RPC URL is empty for chain_id {expected_chain_id}: "
            "set BASE_RPC_URL or rpc_url"
        )

    dex = str(config.get("dex", DEFAULT_DEX)).strip().lower()

    if dex not in SUPPORTED_DEXES:
        raise ValueError(
            f"dex must be one of {', '.join(SUPPORTED_DEXES)}"
        )

    dexes = network_config.get("dexes")

    if not isinstance(dexes, dict):
        raise ValueError(
            f"chain_id {expected_chain_id}: dexes must map DEX names to "
            "their pool, position manager, swap router and quoter settings"
        )

    profile = dexes.get(dex)

    if not isinstance(profile, dict):
        raise ValueError(
            f"dexes.{dex} is missing or is not a mapping; add the settings "
            "for the selected DEX"
        )

    pool_config = _mapping(profile.get("pool"), f"dexes.{dex}.pool")
    position_manager_config = _mapping(
        profile.get("position_manager"),
        f"dexes.{dex}.position_manager",
    )
    swap_router_config = _mapping(
        profile.get("swap_router"),
        f"dexes.{dex}.swap_router",
    )
    quoter_config = _mapping(
        profile.get("quoter"),
        f"dexes.{dex}.quoter",
    )

    pool_address = _required_address(
        pool_config.get("address", ""),
        f"dexes.{dex}.pool.address",
    )
    position_manager_address = _required_address(
        position_manager_config.get("address", ""),
        f"dexes.{dex}.position_manager.address",
    )
    wallet_address = str(config["wallet"]["address"]).strip()

    if not wallet_address:
        raise ValueError("Wallet address is empty")

    raw_token_id = position_manager_config.get("token_id")
    if raw_token_id is None:
        position_token_id = None
    else:
        position_token_id = _to_positive_int(
            raw_token_id,
            f"dexes.{dex}.position_manager.token_id",
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
        swap_router_config.get("address", ""),
        f"dexes.{dex}.swap_router.address",
    )

    quoter_address = _optional_address(
        quoter_config.get("address", ""),
        f"dexes.{dex}.quoter.address",
    )

    oracle_config = _mapping(
        network_config.get("oracle"),
        f"chain_id {expected_chain_id}.oracle",
    )
    weth_config = _mapping(
        network_config.get("weth"),
        f"chain_id {expected_chain_id}.weth",
    )

    weth_address = _optional_address(
        weth_config.get("address", DEFAULT_WETH_ADDRESS),
        "weth.address",
    )

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
        dex=dex,
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
