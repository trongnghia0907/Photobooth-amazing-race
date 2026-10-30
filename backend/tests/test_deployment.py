"""Built deployment boundary tests. No network exposure or hardware output."""
from dataclasses import replace
from pathlib import Path
import hashlib
import secrets
import sqlite3
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.public_main import create_public_app
from app.services.sharing import public_origin
from test_sessions import key, image
from test_printing import login


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path/'runtime',frontend_dist=Path(__file__).resolve().parents[2]/'frontend/dist-host',
                    booth_pairing_key=secrets.token_urlsafe(24),admin_username='operator',admin_password=secrets.token_urlsafe(24),
                    app_env='development',public_base_url='http://localhost:8000',camera_guest_enabled=True)


def pair(client,settings):
    client.cookies.clear()
    response=client.post('/api/booth/pair',headers={'X-OSA-Pair':'1'},json={'key':settings.booth_pairing_key})
    assert response.status_code==200,response.text
    auth={'Cookie':'osa_booth='+client.cookies.get('osa_booth'),'X-Booth-CSRF':response.json()['csrf_token'],
          'Authorization':'Bearer '+secrets.token_hex(32)}
    client.cookies.clear()
    return auth


def operation(auth):return {**auth,'Idempotency-Key':key()}


def create(client,auth,count=4):
    result=client.post('/api/sessions',headers=operation(auth),json={'layout':'landscape_4' if count==4 else 'grid2x3','slot_count':count})
    assert result.status_code==200,result.text
    return result.json()['session_id']


def finalized(client,auth,count=4):
    sid=create(client,auth,count)
    for slot in range(count):
        state=client.post(f'/api/sessions/{sid}/photos',headers=operation(auth),data={'slot_index':slot,'source':'demo'},files={'file':('test.png',image(),'image/png')})
        assert state.status_code==200,state.text
    result=client.put(f'/api/sessions/{sid}/composite',headers=operation(auth),data={'shots_revision':state.json()['shots_revision'],'editor_json':'{}'},files={'file':('final.png',image('green'),'image/png')})
    assert result.status_code==200,result.text
    body={'composite_id':result.json()['composite']['id']}
    assert client.post(f'/api/sessions/{sid}/complete',headers=operation(auth),json=body).status_code==200
    result=client.post(f'/api/sessions/{sid}/finalize',headers=operation(auth),json=body)
    assert result.status_code==200,result.text
    return sid,result.json()


def test_built_routes_station_isolation_csrf_and_logout(settings):
    with TestClient(create_app(settings),client=('127.0.0.1',123)) as client:
        assert client.get('/').status_code==200
        assert client.get('/booth').status_code==200
        for url in ['/docs','/openapi.json','/.env','/runtime/photobooth.sqlite3','/api/not-a-route']:
            assert client.get(url).status_code==404
        assert client.post('/api/sessions',json={}).status_code==401
        assert client.post('/api/booth/pair',json={'key':settings.booth_pairing_key}).status_code==403
        a=pair(client,settings);sid=create(client,a)
        assert client.get(f'/api/sessions/{sid}',headers=a).status_code==200
        assert client.post('/api/sessions',headers={k:v for k,v in a.items() if k!='X-Booth-CSRF'},json={}).status_code==403
        b=pair(client,settings)
        assert client.get(f'/api/sessions/{sid}',headers={**a,'Cookie':b['Cookie']}).status_code==404
        assert client.get(f'/api/sessions/{sid}',headers={**a,'Authorization':b['Authorization']}).status_code==404
        assert client.get('/api/admin/sessions',headers=a).status_code==401
        assert client.post('/api/booth/logout',headers=a).status_code==200
        assert client.get(f'/api/sessions/{sid}',headers=a).status_code==401
        # Re-pairing the same browser renews its station, preserving recovery bindings.
        client.cookies.set('osa_booth',a['Cookie'].split('=',1)[1])
        result=client.post('/api/booth/pair',headers={'X-OSA-Pair':'1'},json={'key':settings.booth_pairing_key})
        assert result.status_code==200
        assert client.get(f'/api/sessions/{sid}',headers=a).status_code==200


def test_public_gateway_only_serves_specific_completed_photo_and_restart(settings):
    with TestClient(create_app(settings),client=('127.0.0.1',123)) as private:
        a=pair(private,settings);sid,one=finalized(private,a,6)
        b=pair(private,settings);sid2,two=finalized(private,b,4)
        assert one['share']['share_url']!=two['share']['share_url']
        paths=[one['share']['download_url'],two['share']['download_url']]
        with TestClient(create_public_app(settings)) as public:
            downloads=[public.get(path).content for path in paths]
            for state in [one,two]:
                assert public.get(state['share']['share_url']).status_code==200
                assert public.get(state['share']['qr_image_url']).status_code==200
            for route in ['/','/booth','/admin','/api/admin/sessions','/api/sessions','/docs','/openapi.json','/.env','/assets/index.js','/p/invalid',one['share']['share_url']+'/../'+sid2]:
                assert public.get(route).status_code==404,route
            assert not hasattr(public.app.state,'camera') and not hasattr(public.app.state,'printing')
        login(private,settings)
        assert private.get('/api/admin/sessions').json()['total']==2
    with TestClient(create_app(settings),client=('127.0.0.1',123)) as private:
        assert private.get(f'/api/sessions/{sid}',headers=a).json()['share']['share_url']==one['share']['share_url']
        login(private,settings)
        assert private.get('/api/admin/sessions').json()['total']==2
    with TestClient(create_public_app(settings)) as public:
        assert [public.get(path).content for path in paths]==downloads


def test_remote_admin_denied_and_secure_production_cookie(settings):
    production=replace(settings,app_env='production',public_base_url='https://photos.example.test')
    with TestClient(create_app(production),base_url='https://localhost',client=('192.168.1.22',321)) as client:
        assert client.get('/admin',headers={'X-Forwarded-For':'127.0.0.1'}).status_code==403
        assert client.post('/api/admin/login',json={}).status_code==403
        response=client.post('/api/booth/pair',headers={'X-OSA-Pair':'1'},json={'key':settings.booth_pairing_key})
        assert response.status_code==200
        cookie=response.headers['set-cookie'].lower()
        assert 'secure' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie
        auth={'X-Booth-CSRF':response.json()['csrf_token'],'Authorization':'Bearer '+secrets.token_hex(32)}
        sid=create(client,auth)
        assert client.post(f'/api/sessions/{sid}/photos',headers=operation(auth)).status_code==403
        assert client.get('/api/sessions',headers={'Origin':'https://evil.example'}).headers.get('access-control-allow-origin') is None


def test_pair_and_station_operation_rate_limits(settings):
    with TestClient(create_app(settings)) as client:
        for _ in range(5):assert client.post('/api/booth/pair',headers={'X-OSA-Pair':'1'},json={'key':'wrong'}).status_code==401
        assert client.post('/api/booth/pair',headers={'X-OSA-Pair':'1'},json={'key':'wrong'}).status_code==429
        client.app.state.booth_access.limiter.entries.clear()
        a=pair(client,settings)
        for _ in range(12):create(client,a)
        assert client.post('/api/sessions',headers=operation(a),json={'layout':'landscape_4','slot_count':4}).status_code==429


def test_lan_origin_explicit_development_only(settings):
    assert public_origin('http://192.168.1.20:8000',allow_lan=True)=='http://192.168.1.20:8000'
    for origin in ['http://192.168.1.20:8000','http://8.8.8.8','http://192.168.1.20.evil.test','http://192.168.1.20/path']:
        with pytest.raises(Exception):public_origin(origin)
    with pytest.raises(ValueError):replace(settings,app_env='production',allow_lan_http=True)


def test_lan_finalization_returns_real_lan_qr_and_warning(settings):
    from io import BytesIO
    from PIL import Image
    import zxingcpp
    lan=replace(settings,public_base_url='http://192.168.1.20:8000',allow_lan_http=True)
    with TestClient(create_app(lan)) as client:
        assert client.get('/api/health').json()['sharing']['lan_only']
        auth=pair(client,lan);sid,state=finalized(client,auth)
        share=state['share']
        assert share['lan_only'] and not share['local_only']
        decoded=zxingcpp.read_barcode(Image.open(BytesIO(client.get(share['qr_image_url']).content)))
        assert decoded.text==share['share_url']
        assert decoded.text.startswith('http://192.168.1.20:8000/p/')


def test_upgrade_preserves_preexisting_completed_files(settings,monkeypatch):
    # Simulate an old schema-6 final whose cleanup never ran. Upgrade must not erase it.
    with TestClient(create_app(settings)) as client:
        repo=client.app.state.repository
        repo.temporary_assets.stop()
        monkeypatch.setattr(repo.temporary_assets,'process_session',lambda *a:None)
        auth=pair(client,settings);sid,state=finalized(client,auth)
    files={str(p.relative_to(settings.storage_root)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in settings.storage_root.rglob('*') if p.is_file() and p.suffix in ('.jpg','.png')}
    assert len(list((settings.storage_root/'originals'/sid).glob('*.png')))==4
    with sqlite3.connect(settings.storage_root/'photobooth.sqlite3') as db:db.execute('PRAGMA user_version=6')
    with TestClient(create_app(settings)) as client:
        with client.app.state.repository.db.connect() as db:
            assert db.execute('PRAGMA user_version').fetchone()[0]==8
            assert db.execute('SELECT cleanup_status FROM session_finals WHERE session_id=?',(sid,)).fetchone()[0]=='retained_legacy'
        for relative,digest in files.items():assert hashlib.sha256((settings.storage_root/relative).read_bytes()).hexdigest()==digest
        assert client.get(state['share']['download_url']).status_code==200
