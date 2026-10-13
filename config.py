from dataclasses import dataclass
import yaml


@dataclass(frozen=True)
class AppConfig:
    rpc_url: str
    pool_address: str
    range_half_width: float
    fee_threshold_usd: float
    check_interval: int
    expected_chain_id: int
    network: str
    dex: str
    position_manager_address: str
    position_token_id: int | None
    wallet_address: str
    token0_usd_feed: str
    token1_usd_feed: str
    oracle_max_age_seconds: int


def load_config() -> AppConfig:
    with open("config.yaml", "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    network = config["network"]
    networks = config["networks"]

    if network not in networks:
        raise ValueError(f"Unknown network: {network}")

    network_config = networks[network]

    rpc_url = network_config["rpc_url"].strip()
    expected_chain_id = int(network_config["chain_id"])

    if not rpc_url:
        raise ValueError("RPC URL is empty")

    pool_address = config["pool"]["address"].strip()

    if not pool_address:
        raise ValueError("Pool address is empty")

    position_manager_address = config["position_manager"]["address"].strip()
    wallet_address = config["wallet"]["address"].strip()
    raw_token_id = config["position_manager"].get("token_id")
    if raw_token_id is None:
        position_token_id = None
    else:
        if isinstance(raw_token_id, bool):
            raise ValueError("position_manager.token_id must be a positive integer")
        try:
            position_token_id = int(raw_token_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("position_manager.token_id must be a positive integer") from exc
        if position_token_id <= 0 or str(position_token_id) != str(raw_token_id):
            raise ValueError("position_manager.token_id must be a positive integer")

    oracle_config = config.get("oracle", {})
    return AppConfig(
        rpc_url=rpc_url,
        pool_address=pool_address,
        range_half_width=config["strategy"]["range_half_width"],
        fee_threshold_usd=float(config["strategy"]["fee_threshold_usd"]),
        check_interval=config["strategy"]["check_interval"],
        expected_chain_id=expected_chain_id,
        network=network,
        dex=str(config.get("dex", "pancakeswap_v3")).strip().lower(),
        position_manager_address=position_manager_address,
        position_token_id=position_token_id,
        wallet_address=wallet_address,
        token0_usd_feed=str(oracle_config.get("token0_usd_feed", "")).strip(),
        token1_usd_feed=str(oracle_config.get("token1_usd_feed", "")).strip(),
        oracle_max_age_seconds=int(oracle_config.get("max_age_seconds", 3600)),
    )
