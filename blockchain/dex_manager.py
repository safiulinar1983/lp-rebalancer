from web3 import Web3

from blockchain.interfaces import PoolAdapter
from blockchain.pancake_v3 import PancakeV3Pool


class DEXManager:
    """Creates pool adapters without coupling strategy code to a DEX."""

    SUPPORTED_DEXES = {"pancakeswap_v3"}

    @classmethod
    def create_pool(
        cls,
        dex_name: str,
        w3: Web3,
        pool_address: str,
    ) -> PoolAdapter:
        name = dex_name.strip().lower()

        if name == "pancakeswap_v3":
            return PancakeV3Pool(w3=w3, address=pool_address)

        supported = ", ".join(sorted(cls.SUPPORTED_DEXES))
        raise ValueError(
            f"Unsupported DEX: {dex_name!r}. Supported DEXes: {supported}"
        )
