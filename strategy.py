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
    token_id: int
    token0: str
    token1: str
    fee: int
    lower_tick: int
    upper_tick: int
    liquidity: int
    tokens_owed0: int
    tokens_owed1: int


class Strategy:
    def __init__(
        self,
        range_half_width: Decimal,
        fee_threshold_usd: Decimal = Decimal("0.10"),
    ):
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
        lower_tick = position.lower_tick
        upper_tick = position.upper_tick

        in_range = is_tick_in_range(
            state.tick,
            lower_tick,
            upper_tick,
        )

        if not in_range:
            action = "REBALANCE"
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
        )
