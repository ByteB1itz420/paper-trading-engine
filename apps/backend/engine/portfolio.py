from dataclasses import dataclass
from decimal import Decimal
from .models import D, Fill


@dataclass
class Position:
    quantity: Decimal = D('0')
    average: Decimal = D('0')
    realized: Decimal = D('0')


class Portfolio:
    def __init__(self, initial: Decimal, symbols: tuple[str, ...]):
        self.initial = initial
        self.cash = initial
        self.positions = {symbol: Position() for symbol in symbols}
        self.fees = D('0')
        self.trades = 0
        self.wins = 0
        self.peak = initial
        self.max_drawdown = D('0')
        self.day_start_equity = initial
        self.day = ''
        self.marks: dict[str, Decimal] = {}

    def apply(self, fill: Fill) -> Decimal:
        p = self.positions[fill.symbol]
        delta = fill.quantity if fill.side == 'BUY' else -fill.quantity
        old, new = p.quantity, p.quantity + delta
        price = fill.execution_price
        closed = min(abs(old), abs(delta)) if old * delta < 0 else D('0')
        pnl = closed * (price - p.average) * (D('1') if old > 0 else D('-1'))
        if closed:
            p.realized += pnl
            if pnl - fill.fee > 0:
                self.wins += 1
        if new == 0:
            p.average = D('0')
        elif old == 0 or old * new < 0:
            p.average = price
        elif old * delta > 0:
            p.average = (abs(old) * p.average + abs(delta) * price) / abs(new)
        p.quantity = new
        self.cash -= delta * price + fill.fee
        self.fees += fill.fee
        self.trades += 1
        return pnl

    def equity(self) -> Decimal:
        return self.cash + sum((p.quantity * self.marks.get(s, p.average) for s, p in self.positions.items()), D('0'))

    def snapshot(self) -> dict:
        equity = self.equity()
        self.peak = max(self.peak, equity)
        self.max_drawdown = max(self.max_drawdown, self.peak - equity)
        rows = {s: {'quantity': p.quantity, 'average': p.average, 'realized': p.realized,
                    'unrealized': p.quantity * (self.marks.get(s, p.average) - p.average),
                    'exposure': abs(p.quantity * self.marks.get(s, p.average))}
                for s, p in self.positions.items()}
        return {'cash': self.cash, 'equity': equity, 'pnl': equity - self.initial,
                'return_pct': (equity / self.initial - 1) * 100, 'drawdown': self.max_drawdown, 'current_drawdown': self.peak - equity,
                'fees': self.fees, 'trades': self.trades, 'win_rate': D(self.wins) / self.trades if self.trades else D('0'),
                'positions': rows, 'daily_pnl': equity - self.day_start_equity}
