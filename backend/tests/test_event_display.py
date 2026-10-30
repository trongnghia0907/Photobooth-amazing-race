"""Explicit consent + read-only projector access, independent of QR and Host."""
from dataclasses import replace
from io import BytesIO
from pathlib import Path
import hashlib
import secrets
import sqlite3
import time
from urllib.parse import urlsplit
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.config import Settings
from app.main import create_app
from app.public_main import create_public_app
from test_sessions import create,upload,composite,headers,key,image
from test_sharing import finalized
from test_printing import login


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path/'runtime',app_env='development',public_base_url='http://localhost:8000',
                    admin_username='gallery-host',admin_password=secrets.token_urlsafe(24))


def saved(client,count=4,color='green'):
    sid=create(client,layout='landscape_4' if count==4 else 'grid2x3',slot_count=count)
    for index in range(count):state=upload(client,sid,index).json()
    size=(1200,800) if count==4 else (800,1200)
    state=composite(client,sid,state['shots_revision'],payload=image(color,size)).json()
    result=client.post(f'/api/sessions/{sid}/complete',headers=headers(key()),json={'composite_id':state['composite']['id']})
    assert result.status_code==200,result.text
    return sid,result.json()


def approve(client,sid,csrf,**body):
    return client.put('/api/admin/event-display/photos/'+sid,headers=csrf,
                      json={'approved':True,'approval_basis':'guest_consent','consent_confirmed':True,**body})


def enable(client,csrf):
    response=client.post('/api/admin/event-display/access',headers=csrf)
    assert response.status_code==200,response.text
    code=response.json()['code']
    result=client.post('/event-display/unlock',headers={'X-OSA-Display':'1'},json={'code':code})
    assert result.status_code==200,result.text
    return code


def test_default_private_consent_required_and_only_official_final(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get('/event-display').status_code==200
        assert client.get('/event-display/api/photos').status_code==401
        sid,state=saved(client)
        assert client.put('/api/admin/event-display/photos/'+sid,json={'approved':True}).status_code==401
        csrf=login(client,settings)
        assert not client.get('/api/admin/event-display/status').json()['enabled']
        enable(client,csrf)
        assert client.get('/event-display/api/photos').json()=={'items':[]}
        assert approve(client,sid,{}).status_code==403
        assert approve(client,sid,csrf,consent_confirmed=False).status_code==422
        assert approve(client,sid,csrf,approval_basis=None).status_code==422
        draft=create(client)
        assert approve(client,draft,csrf).status_code==409
        assert approve(client,sid,csrf).status_code==200
        first=client.get('/event-display/api/photos').json()['items']
        assert len(first)==1 and set(first[0])=={'id','image_url','width','height','approved_at'}
        body=client.get('/event-display/api/photos').text
        for forbidden in [sid,state['composite']['id'],'share','download','path','originals','composites','api/admin']:
            assert forbidden not in body
        displayed=client.get(first[0]['image_url'])
        assert displayed.status_code==200 and displayed.headers['cache-control']=='no-store'
        assert 'attachment' not in displayed.headers.get('content-disposition','')
        assert hashlib.sha256(displayed.content).hexdigest()==state['composite']['sha256']
        assert approve(client,sid,csrf).status_code==200
        assert client.get('/event-display/api/photos').json()['items']==first
        assert client.get('/api/admin/sessions/'+sid).json()['event_display']['approved']


def test_four_six_latest_hide_reapprove_preserves_original_and_qr(settings):
    with TestClient(create_app(settings)) as client:
        a,_,state=finalized(client,'red')
        b,second=saved(client,4)
        original_share=state['share']
        download=client.get(original_share['download_url']).content
        csrf=login(client,settings);enable(client,csrf)
        assert approve(client,a,csrf).status_code==200
        first=client.get('/event-display/api/photos').json()['items'][0]
        assert approve(client,b,csrf,approval_basis='event_authorization').status_code==200
        photos=client.get('/event-display/api/photos').json()['items']
        assert len(photos)==2 and photos[1]['id']==first['id']
        assert (photos[0]['width'],photos[0]['height'])==(1200,800)
        response=approve(client,a,csrf,approved=False)
        assert response.status_code==200
        assert len(client.get('/event-display/api/photos').json()['items'])==1
        assert client.get(first['image_url']).status_code==404
        assert client.get(original_share['download_url']).content==download
        assert client.get('/api/admin/sessions/'+a).json()['composites'][0]['id']==state['composite']['id']
        assert approve(client,a,csrf).status_code==200
        assert client.get('/event-display/api/photos').json()['items'][0]['id']==first['id']
        with client.app.state.repository.db.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM shares WHERE session_id=?',(a,)).fetchone()[0]==1
            assert db.execute('SELECT COUNT(*) FROM event_display_photos WHERE session_id=?',(a,)).fetchone()[0]==1


def test_display_cookie_has_no_host_owner_or_public_gateway_privileges(settings):
    with TestClient(create_app(settings)) as client:
        sid,_=saved(client)
        csrf=login(client,settings);enable(client,csrf);approve(client,sid,csrf)
        media=client.get('/event-display/api/photos').json()['items'][0]['image_url']
        token=client.cookies.get('osa_event_display');client.cookies.clear()
        assert client.get(media).status_code==401
        client.cookies.set('osa_event_display',token,path='/event-display')
        assert client.get(media).status_code==200
        assert client.get('/event-display/api/photos').status_code==200
        assert client.get('/api/admin/sessions').status_code==401
        assert client.get('/api/sessions/'+sid).status_code==401
        assert client.post('/api/admin/event-display/access',headers=csrf).status_code==401
        assert client.post('/event-display/lock').status_code==403
        assert client.post('/event-display/lock',headers={'X-OSA-Display':'1'}).status_code==200
        assert client.get('/event-display/api/photos').status_code==401
    with TestClient(create_public_app(settings)) as public:
        for path in ['/event-display','/event-display/api/photos','/event-display/assets/display.js','/api/admin/event-display/status']:
            assert public.get(path).status_code==404


def test_code_rotation_revocation_expiry_rate_and_secure_cookie(settings):
    with TestClient(create_app(settings)) as client:
        csrf=login(client,settings);old=enable(client,csrf)
        new=client.post('/api/admin/event-display/access',headers=csrf).json()['code']
        assert new!=old and client.get('/event-display/api/photos').status_code==401
        assert client.post('/event-display/unlock',headers={'X-OSA-Display':'1'},json={'code':old}).status_code==401
        assert client.post('/event-display/unlock',json={'code':new}).status_code==403
        assert client.post('/event-display/unlock',headers={'X-OSA-Display':'1'},json={'code':new}).status_code==200
        with client.app.state.repository.db.connect() as db:db.execute('UPDATE event_display_sessions SET expires_at=0')
        assert client.get('/event-display/api/photos').status_code==401
        assert client.post('/api/admin/event-display/access/revoke',headers=csrf).status_code==200
        assert client.post('/event-display/unlock',headers={'X-OSA-Display':'1'},json={'code':new}).status_code==401
        # No access code or session bearer is stored verbatim.
        raw=(settings.storage_root/'photobooth.sqlite3').read_bytes()
        assert old.encode() not in raw and new.encode() not in raw
    with TestClient(create_app(settings)) as client:
        for _ in range(5):assert client.post('/event-display/unlock',headers={'X-OSA-Display':'1'},json={'code':'wrong'}).status_code==401
        assert client.post('/event-display/unlock',headers={'X-OSA-Display':'1'},json={'code':'wrong'}).status_code==429
    with TestClient(create_app(replace(settings,app_env='production')),base_url='https://localhost') as client:
        csrf=login(client,settings);enable(client,csrf)
        cookie=client.cookies.get('osa_event_display')
        assert cookie
        result=client.post('/event-display/unlock',headers={'X-OSA-Display':'1'},json={'code':client.post('/api/admin/event-display/access',headers=csrf).json()['code']})
        assert 'Secure' in result.headers['set-cookie'] and 'HttpOnly' in result.headers['set-cookie'] and 'SameSite=strict' in result.headers['set-cookie']


def test_restart_migration_missing_corrupt_files_and_traversal(settings):
    with TestClient(create_app(settings)) as client:
        sid,state=saved(client);csrf=login(client,settings);enable(client,csrf)
        path=settings.storage_root/'composites'/sid/(state['composite']['id']+'.png')
        original=path.read_bytes();path.write_bytes(b'broken')
        assert approve(client,sid,csrf).status_code==409
        path.write_bytes(original);assert approve(client,sid,csrf).status_code==200
        photo=client.get('/event-display/api/photos').json()['items'][0]
        cookie=client.cookies.get('osa_event_display')
        assert client.get('/event-display/media/../../.share-key').status_code==404
    with sqlite3.connect(settings.storage_root/'photobooth.sqlite3') as db:db.execute('PRAGMA user_version=7')
    with TestClient(create_app(settings)) as client:
        client.cookies.set('osa_event_display',cookie,path='/event-display')
        assert client.get('/event-display/api/photos').json()['items'][0]['id']==photo['id']
        assert client.get(photo['image_url']).content==original
        path.unlink()
        assert client.get('/event-display/api/photos').json()['items']==[]
        assert client.get(photo['image_url']).status_code==404


def test_schema7_upgrade_keeps_existing_photos_private_and_unchanged(settings):
    with TestClient(create_app(settings)) as client:
        sid,_,state=finalized(client)
        before=client.get(state['share']['download_url']).content
    with sqlite3.connect(settings.storage_root/'photobooth.sqlite3') as db:
        for table in ['event_display_photos','event_display_sessions','event_display_config']:db.execute('DROP TABLE '+table)
        db.execute('PRAGMA user_version=7')
    with TestClient(create_app(settings)) as client:
        csrf=login(client,settings);enable(client,csrf)
        assert client.get('/event-display/api/photos').json()=={'items':[]}
        assert client.get(state['share']['download_url']).content==before
        assert client.get('/api/admin/sessions/'+sid).json()['event_display']['approved'] is False
        approve(client,sid,csrf)
        item=client.get('/event-display/api/photos').json()['items'][0]
        with client.app.state.repository.db.connect() as db:
            db.execute("UPDATE composites SET path='.share-key' WHERE id=?",(state['composite']['id'],))
        assert client.get(item['image_url']).status_code==404
        assert client.get('/event-display/api/photos').json()=={'items':[]}
