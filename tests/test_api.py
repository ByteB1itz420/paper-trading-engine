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
