"""Shared fixed-point constants and Decimal precision.

All price and liquidity math in this project uses ``Decimal``. The precision is
configured once here so that results never depend on the import order of the
maths modules.
"""

from decimal import Decimal, getcontext

# Precision for general fixed-point calculations.
PRECISION = 60

# Precision for logarithmic tick conversions in ``blockchain.price``.
LOG_PRECISION = 50

# Q96 fixed-point denominator of Uniswap/PancakeSwap V3 sqrt prices.
Q96 = Decimal(2**96)

# V3 tick base: raw price = 1.0001 ** tick.
TICK_BASE = Decimal("1.0001")

getcontext().prec = PRECISION
