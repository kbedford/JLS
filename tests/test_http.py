import json
import threading
import urllib.request
import urllib.error
import pytest
from jls.server import Server
from jls.parser import parse


class FakeStore:
    def __init__(self):
        self.events, self.rejections = [], []
        self.fail = False
    def health(self):
        if self.fail: raise RuntimeError('offline')
        return {'status':'ready'}
    def ingest(self,event):
        if self.fail: raise RuntimeError('offline')
        parse(event)
        self.events.append(event)
        return {'status':'stored'}
    def reject(self,payload,reason):
        self.rejections.append((payload,reason))


@pytest.fixture
def http_server():
    store=FakeStore()
    server=Server(('127.0.0.1',0),store,'x'*32)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    yield server,store
    server.shutdown()
    server.server_close()
    thread.join()


def request(server,body,token='x'*32):
    req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/events',data=body,
                               headers={'Authorization':'Bearer '+token})
    try:
        with urllib.request.urlopen(req) as r: return r.status,json.load(r)
    except urllib.error.HTTPError as e:
        return e.code,json.load(e)


def test_authentication(http_server,event):
    server,store=http_server
    assert request(server,json.dumps(event).encode(),'wrong')[0]==401
    assert not store.events
    assert request(server,json.dumps(event).encode())[0]==200


def test_outage_returns_retry_not_success(http_server,event):
    server,store=http_server
    store.fail=True
    assert request(server,json.dumps(event).encode())[0]==503
    store.fail=False
    assert request(server,json.dumps(event).encode())[0]==200


@pytest.mark.parametrize('body',[b'broken json',b'{}',b'[]',b'{"message":1}',b'{"message":"bad\\u0000", "@timestamp":"2026-10-16T12:00:00Z"}'])
def test_invalid_input_quarantined(http_server,body):
    server,store=http_server
    code,result=request(server,body)
    assert code==200 and result['status']=='quarantined'
    assert len(store.rejections)==1 and not store.events


def test_size_bound(http_server):
    server,_=http_server
    assert request(server,b'x'*262145)[0]==413
