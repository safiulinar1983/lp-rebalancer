"""Strategy decisions for a single LP position.

``Position`` is re-exported from ``blockchain.positions`` for backwards
compatibility; new code should import it from there.
"""

from dataclasses import dataclass
from decimal import Decimal

from blockchain.pancake_v3 import PoolState
from blockchain.positions import Position
from blockchain.price import is_tick_in_range, price_range_ticks

__all__ = ["Position", "Strategy", "StrategyDecision"]


@dataclass(frozen=True)
class StrategyDecision:
    current_tick: int
    lower_tick: int
    upper_tick: int
    in_range: bool
    action: str
    proposed_lower_tick: int | None = None
    proposed_upper_tick: int | None = None


class Strategy:
    """Decide whether an LP position should hold, collect fees or rebalance.

    ``range_half_width`` and ``fee_threshold_usd`` must be ``Decimal`` values.
    The configuration layer converts YAML numbers without passing them through
    binary floats on purpose.
    """

    def __init__(
        self,
        range_half_width: Decimal,
        fee_threshold_usd: Decimal = Decimal("0.10"),
    ):
        if not isinstance(range_half_width, Decimal):
            raise TypeError("range_half_width must be a Decimal")

        if not isinstance(fee_threshold_usd, Decimal):
            raise TypeError("fee_threshold_usd must be a Decimal")

        if range_half_width <= 0:
            raise ValueError("range_half_width must be positive")

        if fee_threshold_usd < 0:
            raise ValueError("fee_threshold_usd must be non-negative")

        self.range_half_width = range_half_width
        self.fee_threshold_usd = fee_threshold_usd

    def evaluate(
        self,
        state: PoolState,
        position: Position,
        fees_value_usd: Decimal = Decimal("0"),
    ) -> StrategyDecision:
        if not isinstance(fees_value_usd, Decimal):
            raise TypeError("fees_value_usd must be a Decimal")

        if fees_value_usd < 0:
            raise ValueError("fees_value_usd must be non-negative")

        lower_tick = position.lower_tick
        upper_tick = position.upper_tick

        in_range = is_tick_in_range(
            state.tick,
            lower_tick,
            upper_tick,
        )

        proposed_lower_tick = None
        proposed_upper_tick = None

        if not in_range:
            action = "REBALANCE"

            proposed_lower_tick, proposed_upper_tick = price_range_ticks(
                state.price,
                self.range_half_width,
                state.tick_spacing,
                state.token0_decimals,
                state.token1_decimals,
            )

            if not proposed_lower_tick <= state.tick < proposed_upper_tick:
                raise ValueError(
                    "Calculated range does not contain the current tick"
                )
        elif fees_value_usd >= self.fee_threshold_usd:
            action = "COLLECT_FEES"
        else:
            action = "HOLD"

        return StrategyDecision(
            current_tick=state.tick,
            lower_tick=lower_tick,
            upper_tick=upper_tick,
            in_range=in_range,
            action=action,
            proposed_lower_tick=proposed_lower_tick,
            proposed_upper_tick=proposed_upper_tick,
        )
