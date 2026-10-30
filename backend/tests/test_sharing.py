from datetime import datetime, timezone
from io import BytesIO
import hashlib
import logging
import sqlite3
from urllib.parse import urlsplit
import uuid
import zxingcpp

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.logging_filters import ShareTokenFilter
from test_sessions import headers, key, image, create, six_photos, composite

PUBLIC='https://photos.osa.test'


@pytest.fixture
def shared_settings(tmp_path):
    return Settings(tmp_path/'sharing',public_base_url=PUBLIC)


def finalized(client, color='red'):
    sid=create(client)
    state=six_photos(client,sid)
    state=composite(client,sid,state['shots_revision'],payload=image(color)).json()
    image_id=state['composite']['id']
    result=client.post(f'/api/sessions/{sid}/complete',headers=headers(key()),json={'composite_id':image_id})
    assert result.status_code==200,result.text
    operation=key()
    result=client.post(f'/api/sessions/{sid}/finalize',headers=headers(operation),json={'composite_id':image_id})
    assert result.status_code==200,result.text
    return sid,operation,result.json()


def test_two_guests_only_their_immutable_composite_and_no_public_gallery(shared_settings):
    with TestClient(create_app(shared_settings)) as client:
        a,_,first=finalized(client,'red')
        b,_,second=finalized(client,'blue')
        assert first['share']['share_url']!=second['share']['share_url']
        pa=urlsplit(first['share']['share_url']).path
        pb=urlsplit(second['share']['share_url']).path
        image_a=client.get(pa+'/image')
        image_b=client.get(pb+'/image')
        assert image_a.status_code==image_b.status_code==200
        assert Image.open(BytesIO(image_a.content)).getpixel((0,0))[:3]==(255,0,0)
        assert Image.open(BytesIO(image_b.content)).getpixel((0,0))[:3]==(0,0,255)
        assert hashlib.sha256(image_a.content).hexdigest()==first['share']['print_ready']['sha256']
        assert client.get(pa+'/download').content==image_a.content
        assert 'attachment;' in client.get(pa+'/download').headers['content-disposition']
        html=client.get(pa)
        assert html.status_code==200 and a not in html.text and b not in html.text
        assert 'gallery' not in html.text and '/api/sessions' not in html.text
        assert html.headers['referrer-policy']=='no-referrer'
        assert 'noindex' in html.headers['x-robots-tag']
        assert "default-src 'none'" in html.headers['content-security-policy']
        qr=Image.open(BytesIO(client.get(pa+'/qr.png').content))
        assert qr.format=='PNG'
        assert zxingcpp.read_barcode(qr).text==first['share']['share_url']
        assert client.get(pa+'/image',params={'session_id':b,'composite_id':second['composite']['id']}).content==image_a.content
        for path in ['/p','/gallery','/runtime','/runtime/composites','/api/photos','/api/shares']:
            assert client.get(path).status_code in (404,405)
        assert client.get(f'/api/sessions/{b}').status_code==401
        # A share token is not a session credential.
        assert client.get(f'/api/sessions/{b}',headers=headers(token=pa.rsplit('/',1)[1])).status_code==404
        # Confirmation seals one official composite and one share per session.
        assert composite(client,a,first['shots_revision'],payload=image('green')).status_code==409
        new=client.post(f'/api/sessions/{a}/finalize',headers=headers(key()),json={'composite_id':first['composite']['id']}).json()
        assert new['share']['share_url']==first['share']['share_url']
        assert client.get(pa+'/image').content==image_a.content


def test_finalize_idempotency_sqlite_token_hash_and_restart(shared_settings):
    with TestClient(create_app(shared_settings)) as client:
        sid,operation,state=finalized(client)
        body={'composite_id':state['composite']['id']}
        assert client.post(f'/api/sessions/{sid}/finalize',headers=headers(operation),json=body).json()==state
        assert client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json=body).json()==state
        assert len(list((shared_settings.storage_root/'qrcodes').rglob('*.png')))==1
    path=urlsplit(state['share']['share_url']).path
    token=path.rsplit('/',1)[1]
    with sqlite3.connect(shared_settings.storage_root/'photobooth.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM shares').fetchone()[0]==1
        stored=db.execute('SELECT token_hash,nonce FROM shares').fetchone()
        assert stored[0]==hashlib.sha256(token.encode()).hexdigest()
        assert token not in str(stored)
        assert all(token not in row[0] for row in db.execute('SELECT result_json FROM operations'))
    with TestClient(create_app(shared_settings)) as restarted:
        assert restarted.get(f'/api/sessions/{sid}',headers=headers()).json()['share']==state['share']
        assert restarted.get(path+'/download').status_code==200
        assert restarted.post(f'/api/sessions/{sid}/finalize',headers=headers(operation),json=body).json()==state


def test_no_share_before_complete_invalid_expired_revoked_tokens(shared_settings):
    with TestClient(create_app(shared_settings)) as client:
        sid=create(client)
        state=six_photos(client,sid)
        state=composite(client,sid,state['shots_revision']).json()
        assert client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json={'composite_id':state['composite']['id']}).status_code==409
        assert not list(shared_settings.storage_root.rglob('qrcodes/*.png'))
        _,_,state=finalized(client)
        path=urlsplit(state['share']['share_url']).path
        for invalid in ['/p/not-valid','/p/'+('z'*43),'/p/'+str(uuid.uuid4())]:
            for suffix in ['', '/image','/download','/qr.png']:
                assert client.get(invalid+suffix).status_code==404
        with sqlite3.connect(shared_settings.storage_root/'photobooth.sqlite3') as db:
            db.execute('UPDATE shares SET expires_at=?',('2000-01-01T00:00:00+00:00',))
        for suffix in ['', '/image','/download','/qr.png']:
            assert client.get(path+suffix).status_code==404
        with sqlite3.connect(shared_settings.storage_root/'photobooth.sqlite3') as db:
            db.execute('UPDATE shares SET expires_at=NULL,revoked_at=?',(datetime.now(timezone.utc).isoformat(),))
        for suffix in ['', '/image','/download','/qr.png']:
            assert client.get(path+suffix).status_code==404


@pytest.mark.parametrize('origin',['','http://localhost:8000','https://localhost','https://127.0.0.1','https://192.168.1.2',
    'https://[::1]','https://user:password@photos.osa.test','https://photos.osa.test/path','https://photos.osa.test?q=1','https://example.com','https://127.1'])
def test_bad_public_base_never_creates_token(tmp_path,origin):
    settings=Settings(tmp_path/'bad-base',public_base_url=origin)
    with TestClient(create_app(settings)) as client:
        sid=create(client)
        state=six_photos(client,sid)
        state=composite(client,sid,state['shots_revision']).json()
        cid=state['composite']['id']
        assert client.post(f'/api/sessions/{sid}/complete',headers=headers(key()),json={'composite_id':cid}).status_code==200
        assert client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json={'composite_id':cid}).status_code==503
        assert client.get(f'/api/sessions/{sid}',headers=headers()).json()['status']=='completed'
        with sqlite3.connect(settings.storage_root/'photobooth.sqlite3') as db:
            assert db.execute('SELECT COUNT(*) FROM shares').fetchone()[0]==0
        assert not (settings.storage_root/'.share-key').exists()


def test_upgrade_v1_database_is_non_destructive(tmp_path):
    from pathlib import Path
    settings=Settings(tmp_path/'upgrade')
    settings.storage_root.mkdir()
    with sqlite3.connect(settings.storage_root/'photobooth.sqlite3') as db:
        db.executescript((Path(__file__).parents[1]/'app/migrations/001_initial.sql').read_text())
    with TestClient(create_app(settings)) as client:
        sid=create(client)
    with TestClient(create_app(settings)) as client:
        assert client.get(f'/api/sessions/{sid}',headers=headers()).status_code==200
        with sqlite3.connect(settings.storage_root/'photobooth.sqlite3') as db:
            assert db.execute('PRAGMA user_version').fetchone()[0]==8


def test_access_log_redacts_share_token():
    token='S'*43
    record=logging.LogRecord('uvicorn.access',logging.INFO,'',0,'%s - "%s %s HTTP/%s" %d',('client','GET',f'/p/{token}/download','1.1',200),None)
    ShareTokenFilter().filter(record)
    assert token not in record.getMessage()
    assert '[redacted]' in record.getMessage()


def test_v2_cached_bearer_urls_are_redacted_on_upgrade(shared_settings):
    import json
    with TestClient(create_app(shared_settings)) as client:
        sid,operation,state=finalized(client)
    token=state['share']['share_url'].rsplit('/',1)[1]
    with sqlite3.connect(shared_settings.storage_root/'photobooth.sqlite3') as db:
        db.execute('UPDATE operations SET result_json=? WHERE session_id=? AND operation_key=?',(json.dumps(state),sid,operation))
        db.execute('PRAGMA user_version=2')
    with TestClient(create_app(shared_settings)) as migrated:
        replay=migrated.post(f'/api/sessions/{sid}/finalize',headers=headers(operation),json={'composite_id':state['composite']['id']})
        assert replay.json()==state
    with sqlite3.connect(shared_settings.storage_root/'photobooth.sqlite3') as db:
        assert all(token not in r[0] for r in db.execute('SELECT result_json FROM operations'))


def test_missing_secret_does_not_silently_rotate_old_links(shared_settings):
    with TestClient(create_app(shared_settings)) as client:
        sid,_,state=finalized(client)
        path=urlsplit(state['share']['share_url']).path
        (shared_settings.storage_root/'.share-key').unlink()
        # Existing tokens still verify by hash; owner URL reconstruction/new
        # issuance refuses to invent a replacement key, preserving identity.
        assert client.get(path+'/image').status_code==200
        assert client.get(f'/api/sessions/{sid}',headers=headers()).status_code==503
        assert not (shared_settings.storage_root/'.share-key').exists()


@pytest.mark.parametrize('origin',['http://localhost:8000','http://127.0.0.1:8000','http://[::1]:8000'])
def test_development_localhost_uses_real_saved_share_with_warning(tmp_path,origin):
    settings=Settings(tmp_path/'local-dev',public_base_url=origin,app_env='development')
    with TestClient(create_app(settings)) as client:
        config=client.get('/api/health').json()['sharing']
        assert config['configured'] is True
        assert config['local_only'] is True
        assert config['app_env']=='development'
        assert 'điện thoại khác' in config['message']
        sid,operation,state=finalized(client)
        assert state['share']['local_only'] is True
        assert state['share']['share_url'].startswith(origin+'/p/')
        path=urlsplit(state['share']['share_url']).path
        downloaded=client.get(path+'/download')
        assert downloaded.status_code==200
        assert hashlib.sha256(downloaded.content).hexdigest()==state['share']['print_ready']['sha256']
        qr=Image.open(BytesIO(client.get(path+'/qr.png').content))
        assert zxingcpp.read_barcode(qr).text==state['share']['share_url']
        assert client.post(f'/api/sessions/{sid}/finalize',headers=headers(operation),json={'composite_id':state['composite']['id']}).json()==state


@pytest.mark.parametrize('origin',['http://192.168.1.2:8000','http://0.0.0.0:8000','http://localhost.evil.test','http://127.0.0.1@evil.test','http://localhost:bad','http://[','http://127.1'])
def test_development_does_not_allow_arbitrary_http_or_malformed_base(tmp_path,origin):
    settings=Settings(tmp_path/'invalid-local',public_base_url=origin,app_env='development')
    with TestClient(create_app(settings)) as client:
        config=client.get('/api/health').json()['sharing']
        assert config['configured'] is False
        assert 'PUBLIC_BASE_URL' in config['message']
        sid=create(client)
        state=six_photos(client,sid)
        state=composite(client,sid,state['shots_revision']).json()
        cid=state['composite']['id']
        client.post(f'/api/sessions/{sid}/complete',headers=headers(key()),json={'composite_id':cid})
        assert client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json={'composite_id':cid}).status_code==503
        with sqlite3.connect(settings.storage_root/'photobooth.sqlite3') as db:
            assert db.execute('SELECT COUNT(*) FROM shares').fetchone()[0]==0


def test_health_explains_missing_base_and_production_localhost(tmp_path,monkeypatch):
    from app.config import Settings
    monkeypatch.delenv('APP_ENV',raising=False)
    monkeypatch.delenv('PUBLIC_BASE_URL',raising=False)
    assert Settings.from_environment().app_env=='production'
    for value in ['', 'http://localhost:8000']:
        with TestClient(create_app(Settings(tmp_path/('unset' if not value else 'production'),public_base_url=value))) as client:
            config=client.get('/api/health').json()['sharing']
            assert config['configured'] is False
            assert config['app_env']=='production'
            assert 'PUBLIC_BASE_URL' in config['message']
            if value:
                assert 'APP_ENV' in config['message']
