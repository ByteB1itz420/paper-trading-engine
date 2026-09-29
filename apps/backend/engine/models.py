from dataclasses import asdict, dataclass
from decimal import Decimal
from datetime import datetime, timezone

D = Decimal


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def serial(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    if hasattr(value, '__dataclass_fields__'):
        return serial(asdict(value))
    return value


@dataclass(frozen=True)
class MarketTick:
    symbol: str
    timestamp: str
    bid: Decimal
    ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    last_price: Decimal | None = None
    last_trade_size: Decimal | None = None
    received_ms: int = 0
    source: str = 'demo'

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2

    @property
    def valid(self) -> bool:
        return self.bid > 0 and self.ask >= self.bid and self.bid_size > 0 and self.ask_size > 0


@dataclass(frozen=True)
class Signal:
    symbol: str
    action: str
    z: Decimal
    price: Decimal
    reason: str
    timestamp: str


@dataclass(frozen=True)
class Fill:
    order_id: str
    symbol: str
    side: str
    quantity: Decimal
    signal_price: Decimal
    execution_price: Decimal
    fee: Decimal
    slippage: Decimal
    timestamp: str
    strategy_reason: str
    realized_pnl: Decimal = D('0')
