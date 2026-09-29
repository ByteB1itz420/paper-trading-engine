import asyncio
from datetime import datetime, timezone
from decimal import Decimal as D
import pytest
from apps.backend.engine.config import Settings
from apps.backend.engine.store import Store
from apps.backend.engine.system import System
from apps.backend.engine.models import MarketTick
from apps.backend.engine.portfolio import Portfolio
from apps.backend.engine.risk import Risk
from apps.backend.engine.market import BinanceFeed


def make_tick(symbol='BTCUSDT', mid=D('100'), now=9999):
    return MarketTick(symbol, datetime.now(timezone.utc).isoformat(), mid-D('1'), mid+D('1'),
                      D('100'), D('100'), mid, D('1'), now)


def test_running_max_drawdown_is_retained():
    p = Portfolio(D('100'), ('BTCUSDT',))
    p.cash = D('90')
    p.positions['BTCUSDT'].quantity = D('1')
    p.marks['BTCUSDT'] = D('10')
    assert p.snapshot()['drawdown'] == 0
    p.marks['BTCUSDT'] = D('3')
    assert p.snapshot()['drawdown'] == 7
    p.marks['BTCUSDT'] = D('8')
    assert p.snapshot()['drawdown'] == 7 and p.snapshot()['current_drawdown'] == 2


def test_limits_insufficient_cash_and_short_collateral():
    p = Portfolio(D('100'), ('BTCUSDT',))
    p.marks['BTCUSDT'] = D('100')
    risk = Risk({'BTCUSDT': D('200')}, D('1000'), 5000)
    assert 'cash' in risk.check(make_tick(), 'BUY', D('2'), p, 9999)
    assert 'collateral' in risk.check(make_tick(), 'SELL', D('2'), p, 9999)
    p.initial = D('100000')
    assert 'top-of-book' in risk.check(make_tick(), 'SELL', D('101'), p, 9999)


@pytest.mark.asyncio
async def test_persists_session_and_restart_is_new(tmp_path):
    url = f'sqlite:///{tmp_path}/run.db'
    cfg = Settings(database_url=url, window=3, entry_z=D('1'), order_notional=D('20'), min_notional=D('10'))
    store = Store(url)
    system = System(cfg, store)
    now = int(__import__('time').time() * 1000)
    await system.on_tick(make_tick('ETHUSDT', D('4000'), now=now))
    for mid in map(D, ['100', '101', '102', '90']):
        await system.on_tick(make_tick(mid=mid, now=now))
    old = system.session
    assert store.recent('fills', old)
    new_system = System(cfg, Store(url))
    assert new_system.session != old and new_system.portfolio.equity() == cfg.initial_capital
    assert store.recent('fills', old)


@pytest.mark.asyncio
async def test_feed_resets_on_disconnect(monkeypatch):
    received = []

    async def put(value):
        received.append(value)

    feed = BinanceFeed(put)
    feed.sequence['BTCUSDT'] = 20
    feed.quotes['BTCUSDT'] = {'bid': D('1')}

    async def fail(_):
        raise OSError('simulated disconnect')

    async def stop(_):
        raise asyncio.CancelledError

    monkeypatch.setattr('apps.backend.engine.market.websockets.connect', fail)
    monkeypatch.setattr('apps.backend.engine.market.asyncio.sleep', stop)
    with pytest.raises(asyncio.CancelledError):
        await feed.run()
    assert feed.connected is False and feed.quotes == {}

@pytest.mark.asyncio
async def test_database_failure_halts_paper_engine(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path}/fail.db'
    cfg = Settings(database_url=url, window=3, entry_z=D('1'), min_notional=D('10'), order_notional=D('20'))
    store = Store(url)
    system = System(cfg, store)
    now = int(__import__('time').time()*1000)
    from sqlalchemy.exc import SQLAlchemyError

    def fail(*_args, **_kwargs):
        raise SQLAlchemyError('simulated failure')

    monkeypatch.setattr(store, 'add', fail)
    await system.on_tick(make_tick(now=now))
    assert system.persistence_failed and system.risk.killed
    assert system.state()['trading'] is False
    await system.on_tick(make_tick(mid=D('90'), now=now))
    assert system.portfolio.trades == 0


def test_atomic_execution_rolls_back_on_db_failure(tmp_path):
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError
    url = f'sqlite:///{tmp_path}/atomic.db'
    store = Store(url)
    with store.engine.begin() as conn:
        conn.execute(text('CREATE TRIGGER reject_fills BEFORE INSERT ON fills BEGIN SELECT RAISE(ABORT, "simulated DB error"); END;'))
    with pytest.raises(SQLAlchemyError):
        store.record_execution('run1','BTCUSDT',{'order_id':'o1'}, {'order_id':'o1'},
                               {'quantity':'1'}, {'equity':'100'})
    assert not store.recent('orders','run1')
    assert not store.recent('positions','run1')
    assert not store.recent('fills','run1')


def test_short_proceeds_do_not_fund_new_long():
    p = Portfolio(D('100'), ('BTCUSDT', 'ETHUSDT'))
    p.positions['BTCUSDT'].quantity = D('-1')
    p.positions['BTCUSDT'].average = D('99')
    p.cash = D('199')
    p.marks.update({'BTCUSDT': D('100'), 'ETHUSDT': D('100')})
    risk = Risk({'BTCUSDT': D('2'), 'ETHUSDT': D('2')}, D('1000'), 5000)
    assert 'cash' in risk.check(make_tick('ETHUSDT'), 'BUY', D('1'), p, 9999)
    assert risk.check(make_tick(), 'BUY', D('1'), p, 9999) is None


@pytest.mark.asyncio
async def test_trade_updates_validate_and_deduplicate():
    async def noop(_):
        pass
    feed = BinanceFeed(noop)
    base = {'stream':'btcusdt@trade','data':{'s':'BTCUSDT','t':1,'p':'101','q':'0.1'}}
    await feed.consume(base)
    assert feed.trades['BTCUSDT']['last_price'] == 101
    base['data']['p'] = '102'
    await feed.consume(base)
    assert feed.trades['BTCUSDT']['last_price'] == 101
    base['data'].update({'t':2,'p':'-1'})
    await feed.consume(base)
    assert feed.trades['BTCUSDT']['last_price'] == 101

@pytest.mark.asyncio
async def test_other_symbol_stale_blocks_new_paper_fill(tmp_path):
    url = f'sqlite:///{tmp_path}/stale.db'
    cfg = Settings(database_url=url, window=3, entry_z=D('1'), order_notional=D('20'), min_notional=D('10'))
    system = System(cfg, Store(url))
    now = int(__import__('time').time() * 1000)
    for mid in map(D, ['100', '101', '102', '90']):
        await system.on_tick(make_tick(mid=mid, now=now))
    assert not system.fills
    assert system.rejections and 'feeds stale' in system.rejections[-1]['reason']
    await system.on_tick(make_tick('ETHUSDT',D('4000'),now=now))
    for mid in map(D, ['100', '101', '102', '90']):
        await system.on_tick(make_tick(mid=mid,now=now))
    assert system.fills
