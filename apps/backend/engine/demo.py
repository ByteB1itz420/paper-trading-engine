"""Deterministic, explicitly synthetic two-symbol market; not historical performance."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal as D
import time
from .models import MarketTick


class DemoFeed:
    def __init__(self, publish):
        self.publish = publish
        self.connected = False
        self.index = 0

    async def run(self):
        self.connected = True
        try:
            while True:
                for symbol, base in [('BTCUSDT', D('100000')), ('ETHUSDT', D('4000'))]:
                    # repeatable waves plus periodic outliers give entry and exit without false live claims
                    step = self.index % 28
                    offset = D(str((step % 11) - 5)) / D('10000')
                    if step == 14:
                        offset = D('-0.004')
                    if step == 21:
                        offset = D('0.004')
                    mid = base * (1 + offset)
                    now = int(time.time() * 1000)
                    tick = MarketTick(symbol, datetime.fromtimestamp(now/1000, timezone.utc).isoformat(),
                                      mid-D('1'), mid+D('1'), D('10'), D('10'), mid, D('0.01'), now, 'synthetic demo')
                    await self.publish(tick)
                self.index += 1
                await asyncio.sleep(0.5)
        finally:
            self.connected = False
