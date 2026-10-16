"""Manual CLI helpers that talk to a live Base RPC endpoint.

Two kinds of scripts live here:

* read-only reports: ``monitor_pool``, ``list_positions``;
* transaction helpers: ``wrap_weth``, ``approve_weth``, ``mint_position``,
  which require ``PRIVATE_KEY`` in ``.env``.

Both invocation styles work::

    python scripts/monitor_pool.py
    python -m scripts.monitor_pool
"""
