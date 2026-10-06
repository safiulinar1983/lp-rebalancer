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
    action: str


@dataclass(frozen=True)
class Position:
    lower_tick: int
    upper_tick: int


class Strategy:
    def __init__(self, range_half_width: Decimal):
        if range_half_width <= 0:
            raise ValueError("range_half_width must be positive")

        self.range_half_width = range_half_width

    def evaluate(self, state: PoolState, position: Position) -> StrategyDecision:
        lower_tick = position.lower_tick
        upper_tick = position.upper_tick

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
            action="HOLD" if in_range else "REBALANCE",
        )
