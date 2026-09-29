import json
from sqlalchemy import create_engine, text
from .models import serial, stamp

SCHEMA = {
    'market_events': 'symbol TEXT, timestamp TEXT, payload TEXT',
    'orders': 'order_id TEXT, symbol TEXT, timestamp TEXT, payload TEXT',
    'fills': 'order_id TEXT, symbol TEXT, timestamp TEXT, payload TEXT',
    'positions': 'symbol TEXT, timestamp TEXT, payload TEXT',
    'portfolio_snapshots': 'symbol TEXT, timestamp TEXT, payload TEXT',
    'risk_events': 'symbol TEXT, timestamp TEXT, payload TEXT',
    'strategy_signals': 'symbol TEXT, timestamp TEXT, payload TEXT',
    'system_events': 'symbol TEXT, timestamp TEXT, payload TEXT',
}


class Store:
    def __init__(self, url: str):
        self.engine = create_engine(url.replace('postgresql://', 'postgresql+psycopg://').replace('postgres://', 'postgresql+psycopg://'), pool_pre_ping=True)
        with self.engine.begin() as conn:
            for table, columns in SCHEMA.items():
                conn.execute(text(f'CREATE TABLE IF NOT EXISTS {table} (id {"BIGSERIAL PRIMARY KEY" if self.engine.dialect.name == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"}, session_id TEXT, {columns})'))

    def add(self, table: str, session: str, symbol: str, payload, timestamp: str | None = None):
        if table not in SCHEMA:
            raise ValueError('Unknown table')
        with self.engine.begin() as conn:
            conn.execute(text(f'INSERT INTO {table} (session_id,symbol,timestamp,payload) VALUES (:s,:y,:t,:p)'),
                         {'s': session, 'y': symbol, 't': timestamp or stamp(), 'p': json.dumps(serial(payload))})


    def record_execution(self, session: str, symbol: str, order: dict, fill: dict,
                         position: dict, portfolio: dict):
        """Write the whole simulated accounting transition atomically."""
        rows = [('orders', order), ('fills', fill), ('positions', position),
                ('portfolio_snapshots', portfolio)]
        with self.engine.begin() as conn:
            for table, payload in rows:
                conn.execute(text(f'INSERT INTO {table} (session_id,symbol,timestamp,payload) '
                                  'VALUES (:s,:y,:t,:p)'),
                             {'s': session, 'y': symbol, 't': stamp(),
                              'p': json.dumps(serial(payload))})

    def recent(self, table: str, session: str, limit: int = 100) -> list[dict]:
        if table not in SCHEMA:
            raise ValueError('Unknown table')
        with self.engine.connect() as conn:
            rows = conn.execute(text(f'SELECT payload FROM {table} WHERE session_id=:s ORDER BY id DESC LIMIT :n'),
                                {'s': session, 'n': limit}).all()
        return [json.loads(row[0]) for row in rows]

    def latest_session(self) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT payload FROM system_events WHERE symbol='SESSION' ORDER BY id DESC LIMIT 1")).first()
        return json.loads(row[0]) if row else None
