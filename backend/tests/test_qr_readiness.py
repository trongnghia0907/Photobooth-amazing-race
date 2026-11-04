"""Focused QR/gateway proofs; synthetic images and isolated SQLite only."""
from io import BytesIO
import json
import threading
import time

import httpx
import pytest
import zxingcpp
from PIL import Image
from fastapi.testclient import TestClient
from app.public_main import create_public_app
from app.services import public_gateway, sharing
from test_drive_storage import setup, confirmed
from test_sessions import headers, key


def install_gateway(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(public_gateway.httpx, 'Client',
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))


def response(request, status=404):
    return httpx.Response(status, text='AMAZING RACE 2026', request=request)


def test_isolation_checks_all_routes_and_retries_only_failed_route(monkeypatch):
    calls = []
    def serve(request):
        calls.append((request.method, request.url.path))
        if request.url.path == '/admin' and calls.count(('GET','/admin')) == 1:
            return response(request, 503)
        return response(request, 405 if request.method == 'POST' else 404)
    install_gateway(monkeypatch, serve)
    result = public_gateway.verify_isolation('https://photos.test')
    assert result['routes'] == len(public_gateway.DENIED)+1
    assert calls.count(('GET','/admin')) == 2
    assert calls.count(('GET','/api/admin/login')) == 1
    assert ('POST','/p/invalid') in calls


@pytest.mark.parametrize('status', [200, 302, 401])
def test_exposed_or_redirected_private_route_fails_closed(monkeypatch, status):
    install_gateway(monkeypatch, lambda req:response(req, status if req.url.path=='/admin' else 404))
    with pytest.raises(public_gateway.GatewayCheckError, match=f'/admin: HTTP {status}') as caught:
        public_gateway.verify_isolation('https://photos.test')
    assert not caught.value.retryable


def test_connection_failure_identifies_route_and_error(monkeypatch):
    def offline(request):raise httpx.ConnectError('unavailable',request=request)
    install_gateway(monkeypatch, offline)
    with pytest.raises(public_gateway.GatewayCheckError, match='/p/invalid: ConnectError') as caught:
        public_gateway.verify_isolation('https://photos.test')
    assert caught.value.retryable


@pytest.mark.parametrize('count', [4,6])
def test_async_qr_is_independent_of_print_and_offline_drive(setup,monkeypatch,count):
    client,repo,fake,settings=setup
    sid,cid=confirmed(client,count)
    fake.offline=True
    repo.drive.process_one()
    gate=threading.Event();entered=threading.Event()
    original=repo.print_ready.backfill
    def slow_print(final_id):
        entered.set()
        assert gate.wait(10)
        original(final_id)
    monkeypatch.setattr(repo.print_ready,'backfill',slow_print)
    proofs=[]
    monkeypatch.setattr(sharing,'verify_isolation',lambda origin:proofs.append(origin))
    request_headers={**headers(key()),'Prefer':'respond-async'}
    result=client.post(f'/api/sessions/{sid}/finalize',headers=request_headers,json={'composite_id':cid})
    assert result.status_code==200,result.text
    share=result.json()['share'];token=share['share_url'].rsplit('/',1)[1]
    assert share['print_ready'] is None and share['expires_at'] is None
    with repo.db.connect() as db:
        fingerprint=db.execute('SELECT sha256 FROM composites WHERE id=?',(cid,)).fetchone()[0]
    real_client=httpx.Client
    def serve(request):return httpx.Response(200,json={'registered':True,'fingerprint':fingerprint})
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(serve),**kwargs))
    try:
        ready=repo.sharing.verify_public(sid,'a'*64)
        assert ready['public_ready'] and ready['expires_at'] and entered.wait(1)
        png=client.get('/p/'+token+'/qr.png')
        assert zxingcpp.read_barcode(Image.open(BytesIO(png.content))).text==ready['share_url']
        retry=client.post(f'/api/sessions/{sid}/finalize',headers=request_headers,json={'composite_id':cid}).json()['share']
        again=repo.sharing.verify_public(sid,'a'*64)
        assert retry['final_id']==share['final_id'] and again['expires_at']==ready['expires_at']
        assert len(proofs)==1
        with repo.db.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM shares').fetchone()[0]==1
            assert db.execute('SELECT state FROM drive_uploads').fetchone()[0]!='SYNCED'
        assert not fake.files
    finally:
        gate.set();repo.print_ready.close()
    with TestClient(create_public_app(settings)) as public:
        public.app.state.repository.drive.client=fake
        assert public.get('/p/'+token).status_code==200
        image=public.get('/p/'+token+'/image')
        assert image.content==public.get('/p/'+token+'/download').content
        assert zxingcpp.read_barcode(Image.open(BytesIO(image.content))).text==ready['share_url']
        assert public.get('/p/'+token+'/status').json()['fingerprint']==fingerprint
        with repo.db.connect() as db:
            source=db.execute('SELECT path FROM composites WHERE id=?',(cid,)).fetchone()[0]
        (settings.storage_root/source).unlink()  # Only this test's disposable fixture.
        assert public.get('/p/'+token+'/status').status_code==503


def test_unverified_origin_never_starts_expiration(setup,monkeypatch):
    client,repo,fake,settings=setup
    sid,cid=confirmed(client)
    repo.sharing.finalize(sid,'a'*64,key(),cid,defer_print=True)
    def unsafe(origin):raise public_gateway.GatewayCheckError('/admin','HTTP 200; expected 404')
    monkeypatch.setattr(sharing,'verify_isolation',unsafe)
    with pytest.raises(Exception) as error:repo.sharing.verify_public(sid,'a'*64)
    assert error.value.status_code==503 and '/admin' in error.value.detail
    with repo.db.connect() as db:assert db.execute('SELECT expires_at FROM shares').fetchone()[0] is None


def test_tunnel_origin_change_keeps_token_and_deadline_and_disconnect_rejects(setup,monkeypatch):
    client,repo,fake,settings=setup
    sid,cid=confirmed(client)
    repo.sharing.finalize(sid,'a'*64,key(),cid,defer_print=True)
    with repo.db.connect() as db:
        fingerprint=db.execute('SELECT sha256 FROM composites WHERE id=?',(cid,)).fetchone()[0]
    real_client=httpx.Client
    def serve(request):return httpx.Response(200,json={'registered':True,'fingerprint':fingerprint})
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(serve),**kwargs))
    marker=settings.storage_root/'.mobile-qr-origin.json'
    issued=[]
    for name in ['first-origin','second-origin']:
        origin=f'https://{name}.trycloudflare.com'
        marker.write_text(json.dumps({'phase':'ready','origin':origin,'isolation_verified':True,'expires_at':time.time()+60}))
        state=repo.sharing.verify_public(sid,'a'*64)
        assert state['share_url'].startswith(origin+'/p/')
        png=client.get(state['qr_image_url'])
        assert zxingcpp.read_barcode(Image.open(BytesIO(png.content))).text==state['share_url']
        issued.append(state)
    assert issued[0]['final_id']==issued[1]['final_id']
    assert issued[0]['expires_at']==issued[1]['expires_at']
    assert issued[0]['share_url'].split('/p/')[1]==issued[1]['share_url'].split('/p/')[1]
    marker.write_text(json.dumps({'phase':'disconnected','expires_at':0}))
    with pytest.raises(Exception) as error:repo.sharing.verify_public(sid,'a'*64)
    assert error.value.status_code==503 and 'disconnected' in error.value.detail
