"""Paper-only API. No authenticated exchange client or real order route exists."""
from pathlib import Path
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .engine.config import Settings
from .engine.store import Store
from .engine.system import System
from .engine.demo import DemoFeed
from .engine.market import BinanceFeed

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
cfg = Settings()
store = Store(cfg.database_url)
sys = System(cfg, store)

@asynccontextmanager
async def lifespan(app: FastAPI):
    sys.feed = DemoFeed(sys.on_tick) if cfg.mode == 'demo' else BinanceFeed(sys.on_tick)
    task = asyncio.create_task(sys.feed.run())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

app = FastAPI(title='Live Paper Trading Engine', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173'], allow_credentials=False,
                   allow_methods=['GET','POST'], allow_headers=['Content-Type','X-Control-Token'])

class Switch(BaseModel):
    enabled: bool

def authorize(token: str | None):
    if not cfg.control_token or token != cfg.control_token:
        raise HTTPException(403, 'Control token required. Read-only public dashboard.')

@app.get('/health')
def health():
    return {'status': 'ok' if sys.feed and sys.feed.connected else 'waiting', 'mode': cfg.mode,
            'connected': bool(sys.feed and sys.feed.connected), 'paper_only': True}

@app.get('/api/market')
def market(): return sys.state()['market']

@app.get('/api/portfolio')
def portfolio(): return sys.state()['portfolio']

@app.get('/api/positions')
def positions(): return sys.state()['portfolio']['positions']

@app.get('/api/trades')
def trades(): return sys.state()['fills']

@app.get('/api/risk')
def risk(): return sys.state()['risk']

@app.get('/api/performance')
def performance():
    s = sys.state()
    return {'curve': s['curve'], 'benchmark': s['benchmark'], 'return_pct': s['portfolio']['return_pct']}

@app.get('/api/config')
def config():
    return {'mode': cfg.mode, 'symbols': cfg.symbols, 'window': cfg.window, 'entry_z': cfg.entry_z,
            'exit_z': cfg.exit_z, 'fee_rate': cfg.fee_rate, 'slippage_bps': cfg.slippage_bps,
            'initial_capital': cfg.initial_capital, 'stale_ms': cfg.stale_ms, 'paper_only': True,
            'short_sales_supported': False}

@app.get('/api/state')
def state(): return sys.state()

@app.post('/api/kill-switch')
async def kill(body: Switch, x_control_token: str | None = Header(default=None)):
    authorize(x_control_token)
    sys.risk.killed = body.enabled
    store.add('risk_events', sys.session, '', {'kill_switch': body.enabled})
    await sys.publish()
    return {'killed': sys.risk.killed}

@app.post('/api/reset-session')
async def reset(x_control_token: str | None = Header(default=None)):
    authorize(x_control_token)
    sys.reset()
    store.add('system_events', sys.session, 'SESSION', {'session_id': sys.session, 'reset': True, 'mode': cfg.mode})
    await sys.publish()
    return {'session': sys.session, 'paper_only': True}

@app.websocket('/ws')
async def stream(ws: WebSocket):
    await ws.accept()
    sys.listeners.add(ws)
    try:
        await ws.send_json(sys.state())
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        sys.listeners.discard(ws)


FRONTEND = Path(__file__).resolve().parent.parent / 'frontend' / 'dist'
if FRONTEND.exists():
    app.mount('/assets', StaticFiles(directory=FRONTEND / 'assets'), name='assets')

    @app.get('/')
    def index():
        return FileResponse(FRONTEND / 'index.html')
