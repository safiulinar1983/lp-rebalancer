"""Helpers shared by the manual CLI scripts.

Importing this module is side effect free: it only defines helpers.
"""

import os

from dotenv import load_dotenv


def private_key() -> str:
    """Return ``PRIVATE_KEY`` from the environment, loading ``.env`` first."""
    load_dotenv()

    key = os.environ.get("PRIVATE_KEY", "").strip()

    if not key:
        raise RuntimeError(
            "PRIVATE_KEY is not set: copy .env.example to .env and add a key"
        )

    return key
