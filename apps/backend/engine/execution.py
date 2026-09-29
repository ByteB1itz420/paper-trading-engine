from decimal import Decimal
from uuid import uuid4
from .models import MarketTick, Signal, Fill


class PaperExecution:
    """No exchange client or authenticated HTTP dependency exists in this module."""

    def __init__(self, fee_rate: Decimal, slippage_bps: Decimal):
        self.fee_rate, self.slippage_bps = fee_rate, slippage_bps

    def fill(self, tick: MarketTick, signal: Signal, side: str, quantity: Decimal) -> Fill:
        if not tick.valid or quantity <= 0 or quantity > (tick.ask_size if side == 'BUY' else tick.bid_size):
            raise ValueError('Invalid quote or insufficient visible top-of-book liquidity')
        base = tick.ask if side == 'BUY' else tick.bid
        slip = base * self.slippage_bps / Decimal('10000')
        price = base + slip if side == 'BUY' else base - slip
        fee = price * quantity * self.fee_rate
        return Fill(uuid4().hex, tick.symbol, side, quantity, signal.price, price, fee, slip,
                    signal.timestamp, signal.reason)
