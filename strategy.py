from dataclasses import dataclass
from decimal import Decimal

from blockchain.pancake_v3 import PoolState
from blockchain.price import is_tick_in_range, price_range_ticks


@dataclass(frozen=True)
class StrategyDecision:
    current_tick: int
    lower_tick: int
    upper_tick: int
    in_range: bool


class Strategy:
    def __init__(self, range_half_width: Decimal):
        if range_half_width <= 0:
            raise ValueError("range_half_width must be positive")

        self.range_half_width = range_half_width

    def evaluate(self, state: PoolState) -> StrategyDecision:
        lower_tick, upper_tick = price_range_ticks(
            current_price=state.price,
            range_width=self.range_half_width,
            tick_spacing=state.tick_spacing,
            token0_decimals=state.token0_decimals,
            token1_decimals=state.token1_decimals,
        )

        in_range = is_tick_in_range(
            state.tick,
            lower_tick,
            upper_tick,
        )

        return StrategyDecision(
            current_tick=state.tick,
            lower_tick=lower_tick,
            upper_tick=upper_tick,
            in_range=in_range,
        )
