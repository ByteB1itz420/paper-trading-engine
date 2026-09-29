"""Binance's anonymous combined bookTicker/trade streams, with provider-independent ticks."""
import asyncio
import json
import logging
import time
from decimal import Decimal as D
from datetime import datetime, timezone
import websockets
from .models import MarketTick

log = logging.getLogger(__name__)
URL = 'wss://data-stream.binance.vision/stream?streams=btcusdt@bookTicker/btcusdt@trade/ethusdt@bookTicker/ethusdt@trade'


class BinanceFeed:
    def __init__(self, publish):
        self.publish = publish
        self.quotes: dict[str, dict] = {}
        self.trades: dict[str, dict] = {}
        self.sequence: dict[str, int] = {}
        self.connected = False
        self.failures = 0
        self.last_trade_ids: dict[str, int] = {}

    async def consume(self, payload: dict) -> None:
        data = payload.get('data', payload)
        symbol = data.get('s')
        if symbol not in {'BTCUSDT', 'ETHUSDT'}:
            return
        kind = payload.get('stream', '').split('@')[-1]
        try:
            if kind == 'bookTicker' or ('b' in data and 'a' in data):
                seq = int(data['u'])
                if seq <= self.sequence.get(symbol, -1):
                    return
                bid, ask = D(data['b']), D(data['a'])
                bs, ass = D(data['B']), D(data['A'])
                if not (bid > 0 and ask >= bid and bs > 0 and ass > 0):
                    raise ValueError('invalid quote')
                self.sequence[symbol] = seq
                self.quotes[symbol] = dict(bid=bid, ask=ask, bid_size=bs, ask_size=ass)
            elif kind == 'trade' or data.get('e') == 'trade':
                trade_id = int(data['t']) if 't' in data else None
                if trade_id is not None and trade_id <= self.last_trade_ids.get(symbol, -1):
                    return
                price, size = D(data['p']), D(data['q'])
                if price <= 0 or size <= 0:
                    raise ValueError('invalid trade')
                if trade_id is not None:
                    self.last_trade_ids[symbol] = trade_id
                self.trades[symbol] = dict(last_price=price, last_trade_size=size)
                return  # strategy advances on quote updates, not an unsynchronized trade event
            else:
                return
            now = int(time.time() * 1000)
            tick = MarketTick(symbol, datetime.fromtimestamp(now / 1000, timezone.utc).isoformat(),
                              **self.quotes[symbol], **self.trades.get(symbol, {}), received_ms=now, source='Binance public Spot')
            await self.publish(tick)
        except (KeyError, ValueError, ArithmeticError) as exc:
            log.warning('[MARKET] ignored malformed event: %s', exc)

    async def run(self) -> None:
        delay = 1
        while True:
            try:
                async with websockets.connect(URL, ping_interval=20, ping_timeout=20, max_queue=256) as ws:
                    self.connected = True
                    delay = 1
                    self.quotes.clear()
                    self.sequence.clear()
                    self.trades.clear()
                    self.last_trade_ids.clear()
                    log.info('[MARKET] connected to public feed')
                    async for message in ws:
                        await self.consume(json.loads(message))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.failures += 1
                log.warning('[MARKET] disconnect: %s; retrying', exc)
            finally:
                self.connected = False
                self.quotes.clear()
                self.trades.clear()
                self.last_trade_ids.clear()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
