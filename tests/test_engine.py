from decimal import Decimal as D
import time
import pytest
from apps.backend.engine.models import MarketTick, Signal
from apps.backend.engine.strategy import MeanReversion
from apps.backend.engine.portfolio import Portfolio
from apps.backend.engine.risk import Risk
from apps.backend.engine.execution import PaperExecution
from apps.backend.engine.config import Settings
from apps.backend.engine.store import Store
from apps.backend.engine.system import System
from apps.backend.engine.market import BinanceFeed

NOW = int(time.time() * 1000)


def tick(symbol='BTCUSDT', bid='99', ask='101', age=0):
    return MarketTick(symbol, '2026-09-29T10:00:00Z', D(bid), D(ask), D('10'), D('10'),
                      D('100'), D('0.1'), NOW-age)


def signal(action='LONG'):
    return Signal('BTCUSDT', action, D('-2.1'), D('100'), 'sample z=-2.1', '2026-09-29T10:00:00Z')


def test_strategy_warmup_entries_and_exits():
    strategy = MeanReversion(3, D('1'), D('0.2'))
    for bid in ['98', '99', '100']:
        assert strategy.on_market_update(tick(bid=bid, ask=str(D(bid)+2)), D('0')) is None
    long = strategy.on_market_update(tick(bid='89', ask='91'), D('0'))
    assert long and long.action == 'LONG' and 'z-score' in long.reason
    exited = strategy.on_market_update(tick(bid='99', ask='101'), D('1'))
    assert exited and exited.action == 'EXIT'
    short = MeanReversion(3, D('1'), D('0.2'))
    for bid in ['98', '99', '100']:
        short.on_market_update(tick(bid=bid, ask=str(D(bid)+2)), D('0'))
    assert short.on_market_update(tick(bid='109', ask='111'), D('0')).action == 'SHORT'


def test_zero_std_and_determinism():
    a = MeanReversion(3, D('1'), D('0.2'))
    b = MeanReversion(3, D('1'), D('0.2'))
    events = [tick(), tick(), tick(), tick(), tick(bid='80', ask='82')]
    assert [a.on_market_update(x, D('0')) for x in events] == [b.on_market_update(x, D('0')) for x in events]
    assert a.on_market_update(tick(bid='0', ask='82'), D('0')) is None


def test_risk_boundaries():
    p = Portfolio(D('100000'), ('BTCUSDT',))
    p.marks['BTCUSDT'] = D('100')
    r = Risk({'BTCUSDT': D('0.5')}, D('2000'), 5000)
    assert r.check(tick(), 'BUY', D('0.1'), p, NOW) is None
    assert 'Position limit' in r.check(tick(), 'BUY', D('0.6'), p, NOW)
    assert 'stale' in r.check(tick(age=6000), 'BUY', D('0.1'), p, NOW)
    assert 'Invalid' in r.check(tick(bid='105', ask='101'), 'BUY', D('0.1'), p, NOW)
    r.killed = True
    assert 'kill' in r.check(tick(), 'BUY', D('0.1'), p, NOW)
    r.killed = False
    p.day_start_equity = D('103000')
    assert 'daily loss' in r.check(tick(), 'BUY', D('0.1'), p, NOW)


def test_execution_and_accounting():
    p = Portfolio(D('100000'), ('BTCUSDT',))
    exe = PaperExecution(D('0.001'), D('10'))
    buy = exe.fill(tick(), signal(), 'BUY', D('1'))
    assert buy.execution_price == D('101.101')
    assert buy.fee == D('0.101101') and buy.slippage == D('0.101')
    assert p.apply(buy) == 0
    p.marks['BTCUSDT'] = D('110')
    assert p.snapshot()['positions']['BTCUSDT']['unrealized'] == D('8.899')
    sell = exe.fill(tick(bid='110', ask='112'), signal('EXIT'), 'SELL', D('1'))
    assert sell.execution_price == D('109.890')
    assert p.apply(sell) == D('8.789')
    assert p.positions['BTCUSDT'].quantity == 0 and p.positions['BTCUSDT'].average == 0
    assert p.equity() == D('100008.578009')
    assert p.fees == D('0.210991')


@pytest.mark.asyncio
async def test_full_flow_and_persistence(tmp_path):
    cfg = Settings(mode='demo', database_url=f'sqlite:///{tmp_path}/paper.db', window=3,
                   entry_z=D('1'), exit_z=D('0.2'), order_notional=D('20'), min_notional=D('10'))
    store = Store(cfg.database_url)
    system = System(cfg, store)
    for bid in ['98', '99', '100', '89', '99']:
        await system.on_tick(tick(bid=bid, ask=str(D(bid)+2)))
    assert len(system.fills) >= 2
    assert len(store.recent('fills', system.session)) == len(system.fills)
    assert store.recent('positions', system.session)
    assert store.recent('portfolio_snapshots', system.session)
    assert system.state()['benchmark'] is None
    await system.on_tick(tick('ETHUSDT', '3999', '4001'))
    assert system.state()['benchmark'] is not None
    system.risk.killed = True
    for bid in ['98', '99', '100', '89']:
        await system.on_tick(tick(bid=bid, ask=str(D(bid)+2)))
    assert store.recent('risk_events', system.session)


@pytest.mark.asyncio
async def test_bookticker_duplicates_and_malformed():
    received = []

    async def put(value):
        received.append(value)

    feed = BinanceFeed(put)
    msg = {'stream': 'btcusdt@bookTicker', 'data': {'s': 'BTCUSDT', 'u': 10,
           'b': '100', 'a': '101', 'B': '2', 'A': '3'}}
    await feed.consume(msg)
    await feed.consume(msg)
    assert len(received) == 1 and received[0].bid == 100
    await feed.consume({'stream': 'btcusdt@bookTicker', 'data': {'s': 'BTCUSDT', 'u': 11,
                       'b': '-2', 'a': '101', 'B': '2', 'A': '3'}})
    assert len(received) == 1
    await feed.consume({'stream': 'btcusdt@trade', 'data': {'s': 'BTCUSDT', 'p': '100.5', 'q': '0.2'}})
    assert len(received) == 1
    msg['data']['u'] = 12
    await feed.consume(msg)
    assert received[-1].last_trade_size == D('0.2')
