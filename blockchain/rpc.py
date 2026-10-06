from urllib.parse import urlsplit, urlunsplit

from web3 import Web3


class BaseRpcClient:
    def __init__(self, rpc_url: str):
        self._rpc_url = rpc_url
        self._web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))

    def chain_id(self) -> int:
        if not self._web3.is_connected():
            raise ConnectionError("Could not connect to Base RPC")
        return int(self._web3.eth.chain_id)

    def block_number(self) -> int:
        if not self._web3.is_connected():
            raise ConnectionError("Could not connect to Base RPC")
        return int(self._web3.eth.block_number)

    def safe_url(self) -> str:
        """
        Never log query parameters from an RPC URL because they may contain
        provider API keys.
        """
        parsed = urlsplit(self._rpc_url)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
