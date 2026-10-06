from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AppConfig:
    rpc_url: str
    expected_chain_id: int = 8453


def load_config() -> AppConfig:
    rpc_url = os.getenv("BASE_RPC_URL", "https://mainnet.base.org").strip()

    if not rpc_url:
        raise ValueError("BASE_RPC_URL is empty")

    return AppConfig(rpc_url=rpc_url)
