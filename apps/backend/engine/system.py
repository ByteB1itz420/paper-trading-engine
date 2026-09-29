import copy
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal as D
from uuid import uuid4
from .config import Settings
from .models import MarketTick, serial, stamp
from .strategy import MeanReversion
from .portfolio import Portfolio
from .risk import Risk
from .execution import PaperExecution
from .store import Store
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)


class System:
    def __init__(self, cfg: Settings, store: Store):
        self.cfg, self.store = cfg, store
        self.listeners: set = set()
        self.feed = None
        self.reset()
        # Fail-closed restart: a fresh paper session, never silently resume stale positions.
        self.store.add('system_events', self.session, 'SESSION', {'session_id': self.session, 'started': stamp(), 'mode': cfg.mode, 'restart_policy': 'new session'})

    def reset(self, session_id: str | None = None):
        self.session = session_id or uuid4().hex
        self.portfolio = Portfolio(self.cfg.initial_capital, self.cfg.symbols)
        self.strategy = MeanReversion(self.cfg.window, self.cfg.entry_z, self.cfg.exit_z)
        self.risk = Risk(dict(zip(self.cfg.symbols, self.cfg.max_positions, strict=True)), self.cfg.max_daily_loss, self.cfg.stale_ms)
        self.executor = PaperExecution(self.cfg.fee_rate, self.cfg.slippage_bps)
        self.market: dict[str, MarketTick] = {}
        self.benchmark_start: dict[str, D] = {}
        self.curve: list[dict] = []
        self.fills: list[dict] = []
        self.rejections: list[dict] = []
        self.signals: list[dict] = []
        self.last_snapshot = 0.0
        self.persistence_failed = False

    def benchmark(self):
        if len(self.benchmark_start) != len(self.cfg.symbols):
            return None
        each = self.cfg.initial_capital / len(self.cfg.symbols)
        equity = sum((each * self.portfolio.marks[s] / self.benchmark_start[s]
                      for s in self.cfg.symbols), D('0'))
        return {'equity': equity, 'return_pct': (equity / self.cfg.initial_capital - 1) * 100}

    def state(self):
        now = int(time.time()*1000)
        stale = {s: s not in self.market or now - self.market[s].received_ms > self.cfg.stale_ms for s in self.cfg.symbols}
        return serial({'mode': self.cfg.mode, 'session': self.session, 'connected': bool(self.feed and self.feed.connected),
                       'market': self.market, 'stale': stale, 'trading': not self.persistence_failed and not self.risk.killed and not self.risk.daily_halt and not any(stale.values()),
                       'risk': {'killed': self.risk.killed, 'daily_halt': self.risk.daily_halt, 'persistence_failed': self.persistence_failed,
                                'max_daily_loss': self.cfg.max_daily_loss, 'max_positions': self.risk.limits,
                                'rejections': self.rejections[-30:]},
                       'portfolio': self.portfolio.snapshot(), 'benchmark': self.benchmark(),
                       'curve': self.curve[-300:], 'fills': self.fills[-50:], 'signals': self.signals[-30:],
                       'updated_at': stamp()})

    async def publish(self):
        from fastapi.websockets import WebSocketDisconnect
        state = self.state()
        for ws in tuple(self.listeners):
            try:
                await ws.send_json(state)
            except (WebSocketDisconnect, RuntimeError, OSError):
                self.listeners.discard(ws)

    async def on_tick(self, tick: MarketTick):
        if self.persistence_failed:
            return
        try:
            await self._process_tick(tick)
        except SQLAlchemyError:
            self.persistence_failed = True
            self.risk.killed = True
            log.exception('[ERROR] database write failed; paper engine halted until process restart')
            await self.publish()

    async def _process_tick(self, tick: MarketTick):
        if not tick.valid or tick.symbol not in self.cfg.symbols:
            return
        self.market[tick.symbol] = tick
        self.portfolio.marks[tick.symbol] = tick.mid
        if tick.symbol not in self.benchmark_start:
            self.benchmark_start[tick.symbol] = tick.mid
        day = datetime.now(timezone.utc).date().isoformat()
        if self.portfolio.day != day:
            if self.portfolio.day:
                self.portfolio.day_start_equity = self.portfolio.equity()
                self.risk.daily_halt = False
            self.portfolio.day = day
        if self.portfolio.equity() - self.portfolio.day_start_equity <= -self.risk.max_loss:
            self.risk.daily_halt = True
        signal = self.strategy.on_market_update(tick, self.portfolio.positions[tick.symbol].quantity)
        if signal:
            data = serial(signal)
            self.signals.append(data)
            self.store.add('strategy_signals', self.session, tick.symbol, data)
            current_position = self.portfolio.positions[tick.symbol].quantity
            side = 'BUY' if signal.action == 'LONG' or (signal.action == 'EXIT' and current_position < 0) else 'SELL'
            qty = abs(self.portfolio.positions[tick.symbol].quantity) if signal.action == 'EXIT' else self.cfg.order_notional / (tick.ask if side == 'BUY' else tick.bid)
            now_ms = int(time.time()*1000)
            other_stale = any(symbol not in self.market or
                              now_ms - self.market[symbol].received_ms > self.cfg.stale_ms
                              for symbol in self.cfg.symbols)
            reason = ('One or more market feeds stale' if other_stale else
                      self.risk.check(tick, side, qty, self.portfolio, now_ms))
            if qty * tick.mid < self.cfg.min_notional:
                reason = reason or 'Below minimum paper notional'
            if reason:
                rejection = {'symbol': tick.symbol, 'action': signal.action, 'reason': reason, 'timestamp': tick.timestamp}
                self.rejections.append(rejection)
                self.store.add('risk_events', self.session, tick.symbol, rejection)
                log.info('[RISK] %s %s', tick.symbol, reason)
            else:
                fill = self.executor.fill(tick, signal, side, qty)
                # One DB transaction for order/fill/position/ledger after computing a candidate.
                # In-memory state changes only after the transaction commits.
                candidate = copy.deepcopy(self.portfolio)
                realized = candidate.apply(fill)
                filled = serial(fill)
                filled['realized_pnl'] = str(realized)
                self.store.record_execution(self.session, tick.symbol,
                    {'order_id': fill.order_id, 'signal': data, 'side': side, 'quantity': qty},
                    filled, serial(candidate.positions[tick.symbol]),
                    serial(candidate.snapshot()))
                self.portfolio = candidate
                self.fills.append(filled)
                log.info('[FILL] %s %s qty=%s price=%s', tick.symbol, side, qty, fill.execution_price)
        now = time.monotonic()
        if now - self.last_snapshot >= 1:
            self.last_snapshot = now
            point = serial({'timestamp': tick.timestamp, 'equity': self.portfolio.equity(),
                            'benchmark': self.benchmark()['equity'] if self.benchmark() else None})
            self.curve.append(point)
            self.store.add('portfolio_snapshots', self.session, '', point)
            for symbol, position in self.portfolio.positions.items():
                self.store.add('positions', self.session, symbol, serial(position))
            # sample market state, not every raw exchange tick
            self.store.add('market_events', self.session, tick.symbol, serial(tick))
        await self.publish()
