from decimal import Decimal
from .models import MarketTick
from .portfolio import Portfolio


class Risk:
    def __init__(self, limits: dict[str, Decimal], max_loss: Decimal, stale_ms: int):
        self.limits, self.max_loss, self.stale_ms = limits, max_loss, stale_ms
        self.killed = False
        self.daily_halt = False

    def check(self, tick: MarketTick, side: str, quantity: Decimal, portfolio: Portfolio, now_ms: int) -> str | None:
        if self.killed:
            return 'Manual kill switch active'
        if self.daily_halt or portfolio.equity() - portfolio.day_start_equity <= -self.max_loss:
            self.daily_halt = True
            return 'Maximum daily loss exceeded'
        if tick.received_ms <= 0 or now_ms - tick.received_ms > self.stale_ms:
            return 'Market data stale'
        if not tick.valid:
            return 'Invalid bid/ask or quantity'
        if quantity <= 0 or side not in {'BUY', 'SELL'}:
            return 'Invalid order'
        signed = quantity if side == 'BUY' else -quantity
        if abs(portfolio.positions[tick.symbol].quantity + signed) > self.limits[tick.symbol]:
            return 'Position limit exceeded'
        # Short positions require collateral not modeled; keep the first implementation long/flat.
        if portfolio.positions[tick.symbol].quantity + signed < 0:
            return 'Short sale unsupported in cash-only paper account'
        estimated = quantity * tick.ask * Decimal('1.01')
        if side == 'BUY' and portfolio.cash < estimated:
            return 'Insufficient paper cash'
        if quantity > (tick.ask_size if side == 'BUY' else tick.bid_size):
            return 'Insufficient visible top-of-book size'
        return None
