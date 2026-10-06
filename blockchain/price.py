
from decimal import Decimal, getcontext

getcontext().prec = 50


Q96 = Decimal(2**96)


def price_token1_in_token0(
    sqrt_price_x96: int,
    token0_decimals: int,
    token1_decimals: int,
) -> Decimal:
    """
    Returns the price of 1 token1 expressed in token0.

    Example:
        token0 = USDC  (6 decimals)
        token1 = cbBTC (8 decimals)

    Result:
        USDC per 1 cbBTC.
    """

    sqrt_price = Decimal(sqrt_price_x96) / Q96

    # token1/token0 in raw atomic units
    raw_price = sqrt_price ** 2

    # Convert to human-readable token1/token0
    token1_per_token0 = raw_price * (
        Decimal(10) ** (token0_decimals - token1_decimals)
    )

    # We need token0 per token1
    return Decimal(1) / token1_per_token0

def align_tick(tick: int, tick_spacing: int, round_up: bool = False) -> int:
    """
    Align a tick to the nearest valid tick for a PancakeSwap V3 pool.

    tick_spacing=10 means valid ticks are ..., -20, -10, 0, 10, 20, ...

    round_up=False:
        round down to the lower valid tick.

    round_up=True:
        round up to the higher valid tick.
    """

    if tick_spacing <= 0:
        raise ValueError("tick_spacing must be positive")

    quotient, remainder = divmod(tick, tick_spacing)

    if remainder == 0:
        return tick

    if round_up:
        return (quotient + 1) * tick_spacing

    return quotient * tick_spacing

def price_from_tick(
    tick: int,
    token0_decimals: int,
    token1_decimals: int,
) -> Decimal:
    """
    Returns the price of 1 token1 expressed in token0
    for a given V3 tick.
    """

    raw_price = Decimal("1.0001") ** tick

    token1_per_token0 = raw_price * (
        Decimal(10) ** (token0_decimals - token1_decimals)
    )

    return Decimal(1) / token1_per_token0

def price_range(
    current_price: Decimal,
    range_width: Decimal,
) -> tuple[Decimal, Decimal]:
    """
    Returns lower and upper prices around the current price.

    Example:
        current_price = 100
        range_width = 0.01

        result:
            99.00, 101.00
    """

    if current_price <= 0:
        raise ValueError("current_price must be positive")

    if range_width <= 0:
        raise ValueError("range_width must be positive")

    half_width = range_width

    lower = current_price * (Decimal(1) - half_width)
    upper = current_price * (Decimal(1) + half_width)

    return lower, upper

def tick_from_price(
    price: Decimal,
    token0_decimals: int,
    token1_decimals: int,
) -> int:
    """
    Returns the approximate V3 tick for a given price.

    Price is expressed as token0 per 1 token1.
    """

    if price <= 0:
        raise ValueError("price must be positive")

    human_token1_per_token0 = Decimal(1) / price

    raw_price = human_token1_per_token0 / (
        Decimal(10) ** (token0_decimals - token1_decimals)
    )

    # log(raw_price) / log(1.0001)
    from decimal import localcontext

    with localcontext() as ctx:
        ctx.prec = 50
        tick = raw_price.ln() / Decimal("1.0001").ln()

    return int(tick)

def price_range_ticks(
    current_price: Decimal,
    range_width: Decimal,
    tick_spacing: int,
    token0_decimals: int,
    token1_decimals: int,
) -> tuple[int, int]:
    """
    Returns valid V3 lower and upper ticks for a price range.

    Price is expressed as token0 per 1 token1.

    For example:
        token0 = USDC
        token1 = cbBTC

    lower price -> higher V3 tick
    upper price -> lower V3 tick
    """

    lower_price, upper_price = price_range(
        current_price,
        range_width,
    )

    lower_price_tick = tick_from_price(
        lower_price,
        token0_decimals,
        token1_decimals,
    )

    upper_price_tick = tick_from_price(
        upper_price,
        token0_decimals,
        token1_decimals,
    )

    # Because our displayed price is token0/token1,
    # the V3 tick direction is reversed.
    lower_tick = align_tick(
        upper_price_tick,
        tick_spacing,
        round_up=False,
    )

    upper_tick = align_tick(
        lower_price_tick,
        tick_spacing,
        round_up=True,
    )

    if lower_tick >= upper_tick:
        raise ValueError("Invalid tick range")

    return lower_tick, upper_tick

def is_tick_in_range(
    tick: int,
    lower_tick: int,
    upper_tick: int,
) -> bool:
    """
    Returns True if the current V3 tick is inside the position range.

    The lower and upper ticks are inclusive.
    """

    if lower_tick >= upper_tick:
        raise ValueError("lower_tick must be less than upper_tick")

    return lower_tick <= tick <= upper_tick
