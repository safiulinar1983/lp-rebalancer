def minimum_amount_out(
    quoted_amount_out_raw: int,
    slippage_bps: int,
) -> int:
    """Calculate the minimum acceptable output in raw token units.

    slippage_bps is expressed in basis points:
    100 bps = 1%, 50 bps = 0.5%.
    """
    if (
        isinstance(quoted_amount_out_raw, bool)
        or not isinstance(quoted_amount_out_raw, int)
        or quoted_amount_out_raw <= 0
    ):
        raise ValueError("Quoted output must be a positive integer")

    if (
        isinstance(slippage_bps, bool)
        or not isinstance(slippage_bps, int)
        or not 0 <= slippage_bps < 10_000
    ):
        raise ValueError(
            "slippage_bps must be an integer from 0 to 9999"
        )

    minimum = (
        quoted_amount_out_raw * (10_000 - slippage_bps)
    ) // 10_000

    if minimum <= 0:
        raise ValueError(
            "Slippage settings produce a zero minimum output"
        )

    return minimum
