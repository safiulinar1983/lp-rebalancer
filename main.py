import logging
import os
import sys

from dotenv import load_dotenv

from blockchain.rpc import BaseRpcClient
from config import load_config


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> int:
    configure_logging()
    load_dotenv()

    try:
        config = load_config()
        rpc = BaseRpcClient(config.rpc_url)

        logging.info("Connecting to Base...")
        chain_id = rpc.chain_id()
        block_number = rpc.block_number()

        logging.info("chain_id=%s", chain_id)
        logging.info("block_number=%s", block_number)

        if chain_id != config.expected_chain_id:
            logging.error(
                "Wrong network: expected chain_id=%s, got=%s",
                config.expected_chain_id,
                chain_id,
            )
            return 2

        logging.info("status=CONNECTED")
        logging.info("network=Base Mainnet")
        logging.info("rpc=%s", rpc.safe_url())
        return 0

    except Exception as exc:
        logging.exception("status=ERROR error=%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
