from collections import deque
from decimal import Decimal, localcontext
from .models import MarketTick, Signal


class MeanReversion:
    """Pure deterministic decision state; current quote is excluded from its baseline."""

    def __init__(self, window: int, entry: Decimal, exit_z: Decimal):
        self.history: dict[str, deque[Decimal]] = {}
        self.window, self.entry, self.exit = window, entry, exit_z

    def on_market_update(self, tick: MarketTick, position: Decimal) -> Signal | None:
        prices = self.history.setdefault(tick.symbol, deque(maxlen=self.window))
        if not tick.valid:
            return None
        mid = tick.mid
        if len(prices) < self.window:
            prices.append(mid)
            return None
        with localcontext() as ctx:
            ctx.prec = 32
            mean = sum(prices) / len(prices)
            variance = sum((x - mean) ** 2 for x in prices) / len(prices)
            z = (mid - mean) / variance.sqrt() if variance else Decimal('0')
        prices.append(mid)
        action = None
        if position > 0:
            if z >= -self.exit:
                action = 'EXIT'
        elif position < 0:
            if z <= self.exit:
                action = 'EXIT'
        elif z < -self.entry:
            action = 'LONG'
        elif z > self.entry:
            action = 'SHORT'
        if action:
            return Signal(tick.symbol, action, z, mid,
                          f'{action}: mid-price z-score {z:.2f}; entry ±{self.entry}, exit ±{self.exit}; prior {self.window} quotes', tick.timestamp)
        return None
