"""Minimal Base RPC client plus a chain-id validating connection helper."""

from urllib.parse import urlsplit, urlunsplit

from web3 import Web3

DEFAULT_TIMEOUT_SECONDS = 15


def safe_rpc_url(rpc_url: str) -> str:
    """Strip query parameters from an RPC URL.

    Provider API keys are usually passed as query parameters, so an RPC URL
    must never be logged verbatim.
    """
    parsed = urlsplit(rpc_url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def connect(
    rpc_url: str,
    expected_chain_id: int,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Web3:
    """Return a connected ``Web3`` client after verifying the chain id.

    Used by ``monitor_position`` and the scripts so that the connection and
    chain checks live in exactly one place.
    """
    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))

    if not web3.is_connected():
        raise ConnectionError(f"Could not connect to RPC: {safe_rpc_url(rpc_url)}")

    chain_id = int(web3.eth.chain_id)

    if chain_id != expected_chain_id:
        raise ValueError(
            f"Wrong chain: expected chain_id={expected_chain_id}, got {chain_id}"
        )

    return web3


class BaseRpcClient:
    def __init__(self, rpc_url: str):
        self._rpc_url = rpc_url
        self._web3 = Web3(
            Web3.HTTPProvider(
                rpc_url,
                request_kwargs={"timeout": DEFAULT_TIMEOUT_SECONDS},
            )
        )

    def chain_id(self) -> int:
        if not self._web3.is_connected():
            raise ConnectionError("Could not connect to Base RPC")
        return int(self._web3.eth.chain_id)

    def block_number(self) -> int:
        if not self._web3.is_connected():
            raise ConnectionError("Could not connect to Base RPC")
        return int(self._web3.eth.block_number)

    def safe_url(self) -> str:
        """Never log query parameters from an RPC URL: they may hold API keys."""
        return safe_rpc_url(self._rpc_url)
