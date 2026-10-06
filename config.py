from dataclasses import dataclass
import os
import yaml
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class AppConfig:
    rpc_url: str
    pool_address: str
    range_half_width: float
    check_interval: int
    expected_chain_id: int = 8453

def load_config() -> AppConfig:
    rpc_url = os.getenv("BASE_RPC_URL", "https://mainnet.base.org").strip()

    if not rpc_url:
        raise ValueError("BASE_RPC_URL is empty")

    with open("config.yaml", "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    pool_address = config["pool"]["address"].strip()

    if not pool_address:
        raise ValueError("Pool address is empty")

    return AppConfig(
        rpc_url=rpc_url,
        pool_address=pool_address,
        range_half_width=config["strategy"]["range_half_width"],
        check_interval=config["strategy"]["check_interval"],
    )
