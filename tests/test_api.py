from fastapi.testclient import TestClient
from apps.backend.main import app, sys


def test_api_and_websocket():
    with TestClient(app) as client:
        health=client.get('/health').json()
        assert health['paper_only'] is True
        for url in ['/api/market','/api/portfolio','/api/positions','/api/trades','/api/risk','/api/performance','/api/config','/api/state']:
            assert client.get(url).status_code==200
        assert client.get('/').status_code==200
        assert client.post('/api/kill-switch',json={'enabled':True}).status_code==403
        with client.websocket_connect('/ws') as ws:
            first=ws.receive_json()
            assert first['mode']=='demo' and first['session']==sys.session
            assert first['portfolio']['equity']


def test_reset_and_kill_switch_require_control_token(monkeypatch):
    from apps.backend import main
    monkeypatch.setattr(main.cfg, 'control_token', 'abc-test') if False else None
    # Settings is frozen, so replace only the module-level config reference for this test.
    from dataclasses import replace
    monkeypatch.setattr(main, 'cfg', replace(main.cfg, control_token='abc-test'))
    with TestClient(app) as client:
        old = client.get('/api/state').json()['session']
        assert client.post('/api/reset-session').status_code == 403
        response = client.post('/api/kill-switch', headers={'X-Control-Token':'abc-test'}, json={'enabled':True})
        assert response.status_code == 200 and response.json()['killed'] is True
        assert client.get('/api/state').json()['risk']['killed'] is True
        response = client.post('/api/reset-session', headers={'X-Control-Token':'abc-test'})
        assert response.status_code == 200
        assert response.json()['session'] != old
        assert client.get('/api/state').json()['risk']['killed'] is False
