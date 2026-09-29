from dataclasses import dataclass
from decimal import Decimal
import os


def dec(name: str, default: str) -> Decimal:
    return Decimal(os.getenv(name, default))


@dataclass(frozen=True)
class Settings:
    mode: str = os.getenv('MODE', 'demo')
    symbols: tuple[str, ...] = tuple(os.getenv('SYMBOLS', 'BTCUSDT,ETHUSDT').split(','))
    initial_capital: Decimal = dec('INITIAL_CAPITAL', '100000')
    window: int = int(os.getenv('STRATEGY_WINDOW', '20'))
    entry_z: Decimal = dec('ENTRY_Z', '1.8')
    exit_z: Decimal = dec('EXIT_Z', '0.5')
    fee_rate: Decimal = dec('FEE_RATE', '0.0004')
    slippage_bps: Decimal = dec('SLIPPAGE_BPS', '2')
    max_daily_loss: Decimal = dec('MAX_DAILY_LOSS', '2000')
    stale_ms: int = int(os.getenv('STALE_DATA_TIMEOUT_MS', '5000'))
    order_notional: Decimal = dec('ORDER_NOTIONAL', '1000')
    min_notional: Decimal = dec('MIN_NOTIONAL', '10')
    max_positions: tuple[Decimal, ...] = (dec('MAX_POSITION_BTC', '0.5'), dec('MAX_POSITION_ETH', '5'))
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./paper.db')
    control_token: str = os.getenv('CONTROL_TOKEN', '')

    def __post_init__(self) -> None:
        if self.mode not in {'live', 'demo'} or self.symbols != ('BTCUSDT', 'ETHUSDT'):
            raise ValueError('MODE must be live or demo and SYMBOLS must be BTCUSDT,ETHUSDT')
        if self.window < 3 or not 0 <= self.exit_z < self.entry_z or self.initial_capital <= 0:
            raise ValueError('Invalid strategy or capital configuration')
        if not (0 <= self.fee_rate < 1 and 0 <= self.slippage_bps < 100 and self.stale_ms > 0):
            raise ValueError('Invalid market/execution configuration')
        if any(x <= 0 for x in (*self.max_positions, self.max_daily_loss, self.min_notional, self.order_notional)):
            raise ValueError('Limits and order size must be positive')
        if self.mode == 'live' and not self.control_token:
            raise ValueError('CONTROL_TOKEN is required in live mode for mutating API controls')
