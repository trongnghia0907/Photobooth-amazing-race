from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
import importlib.util
from pathlib import Path
import secrets
import sys

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.public_main import create_public_app
from test_event_display import saved, approve
from test_printing import login
from test_sessions import create, headers, key


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path/'gallery',app_env='development',public_base_url='https://photos.test',
                    public_gallery_enabled=True,admin_username='gallery-host',admin_password=secrets.token_urlsafe(24))


def publish(client,csrf,index=0,count=4):
    sid,state=saved(client,count,'blue' if count==4 else 'red')
    final=client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json={'composite_id':state['composite']['id']})
    assert final.status_code==200,final.text
    assert approve(client,sid,csrf).status_code==200
    repo=client.app.state.repository
    with repo.db.connect() as db:
        # Simulate the existing verified public issuance, without an external URL.
        expiry=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        db.execute('UPDATE shares SET expires_at=? WHERE session_id=?',(expiry,sid))
        db.execute('UPDATE session_finals SET confirmed_at=? WHERE session_id=?',
                   ((datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=index)).isoformat(),sid))
        display_id=db.execute('SELECT display_id FROM event_display_photos WHERE session_id=?',(sid,)).fetchone()[0]
    return sid,display_id,final.json()['share']


def test_public_gallery_is_opt_in_and_has_no_write_routes(settings,monkeypatch):
    for factory in (create_app,create_public_app):
        with TestClient(factory(replace(settings,public_gallery_enabled=False))) as client:
            for path in ('/gallery','/gallery/api/photos','/gallery/assets/gallery.js'):
                assert client.get(path).status_code==404
    monkeypatch.setenv('PUBLIC_GALLERY_ENABLED','true')
    assert Settings.from_environment().public_gallery_enabled is True
    with TestClient(create_public_app(settings)) as client:
        assert client.get('/gallery').status_code==200
        assert client.get('/gallery/assets/gallery.css').status_code==200
        assert client.get('/gallery/assets/gallery.js').status_code==200
        assert client.post('/gallery/api/photos',json={}).status_code==405
        for path in ('/admin','/api/admin/sessions','/api/admin/camera','/api/admin/print-jobs','/api/sessions','/event-display','/docs'):
            assert client.get(path).status_code==404
        assert not hasattr(client.app.state,'camera') and not hasattr(client.app.state,'printing')
    monkeypatch.setenv('MOBILE_QR_TEST_SESSION_ID','disposable-session-only')
    with TestClient(create_public_app(settings)) as client:
        assert client.get('/gallery').status_code==404


def test_pagination_newest_first_no_duplicates_and_no_share_mutation(settings):
    with TestClient(create_app(settings)) as client:
        csrf=login(client,settings)
        ids=[publish(client,csrf,index,count=4 if index%2==0 else 6)[1] for index in range(23)]
        repo=client.app.state.repository
        with repo.db.connect() as db:
            before=[tuple(row) for row in db.execute('SELECT * FROM shares ORDER BY id')]
        pages=[client.get('/gallery/api/photos?page='+str(n)).json() for n in (1,2,3)]
        assert [len(p['items']) for p in pages]==[10,10,3]
        assert all(p['total']==23 and p['pages']==3 and p['page_size']==10 for p in pages)
        actual=[item['id'] for p in pages for item in p['items']]
        assert actual==list(reversed(ids)) and len(set(actual))==23
        for value,expected in [('nope',1),('-7',1),('0',1),('99999999999',3)]:
            assert client.get('/gallery/api/photos',params={'page':value}).json()['page']==expected
        response=client.get('/gallery/api/photos')
        assert response.headers['cache-control']=='no-store'
        for item in response.json()['items']:
            assert set(item)=={'id','preview_url','photo_url','width','height','expires_at'}
        for private in ('drive_file_id','nonce','token_hash','originals','storage_root','/api/admin'):
            assert private not in response.text
        with repo.db.connect() as db:
            assert before==[tuple(row) for row in db.execute('SELECT * FROM shares ORDER BY id')]
        with TestClient(create_public_app(settings)) as public:
            assert public.get('/gallery/api/photos').json()==pages[0]


@pytest.mark.parametrize('count',[4,6])
def test_contained_thumbnail_and_existing_photo_detail_download(settings,count):
    with TestClient(create_app(settings)) as client:
        csrf=login(client,settings);sid,display_id,share=publish(client,csrf,count=count)
        item=client.get('/gallery/api/photos').json()['items'][0]
        assert item['photo_url']==share['image_url'].removesuffix('/image')
        preview=client.get(item['preview_url'])
        assert preview.status_code==200 and preview.headers['content-type']=='image/jpeg'
        assert preview.headers['cache-control']=='no-store' and 'attachment' not in preview.headers
        image=Image.open(BytesIO(preview.content))
        assert max(image.size)<=600
        assert abs(image.width/image.height-item['width']/item['height'])<.01
        assert client.get(item['photo_url']).status_code==200
        assert client.get(item['photo_url']+'/image').content==client.get(item['photo_url']+'/download').content
        # Revoking event publication leaves the guest's existing private link intact.
        assert approve(client,sid,csrf,approved=False).status_code==200
        assert client.get(item['preview_url']).status_code==404
        assert client.get('/gallery/api/photos').json()['items']==[]
        assert client.get(item['photo_url']).status_code==200


def test_only_published_official_finals_with_issued_unexpired_links(settings):
    with TestClient(create_app(settings)) as client:
        csrf=login(client,settings);repo=client.app.state.repository
        valid,visible,share=publish(client,csrf)
        cases=[publish(client,csrf,index+1) for index in range(5)]
        unapproved,expired,revoked,unissued,unfinished=[item[0] for item in cases]
        with repo.db.connect() as db:
            db.execute('UPDATE event_display_photos SET approved=0 WHERE session_id=?',(unapproved,))
            db.execute("UPDATE shares SET expires_at='2000-01-01T00:00:00+00:00' WHERE session_id=?",(expired,))
            db.execute("UPDATE shares SET revoked_at='2000-01-01T00:00:00+00:00' WHERE session_id=?",(revoked,))
            db.execute('UPDATE shares SET expires_at=NULL WHERE session_id=?',(unissued,))
            db.execute("UPDATE sessions SET status='editing' WHERE id=?",(unfinished,))
        create(client)  # A new unfinished session can never join the feed.
        result=client.get('/gallery/api/photos').json()
        assert result['total']==1 and result['items'][0]['id']==visible
        for _,display_id,_ in cases:
            assert client.get('/gallery/preview/'+display_id).status_code==404
        with repo.db.connect() as db:
            db.execute("UPDATE shares SET expires_at='2000-01-01T00:00:00+00:00' WHERE session_id=?",(valid,))
        assert client.get('/gallery/preview/'+visible).status_code==404
        empty=client.get('/gallery/api/photos?page=100').json()
        assert empty=={'items':[],'total':0,'page':1,'pages':1,'page_size':10}


def test_mobile_gateway_isolation_accepts_only_the_enabled_read_only_gallery(settings,monkeypatch):
    scripts=Path(__file__).resolve().parents[2]/'scripts';sys.path.insert(0,str(scripts))
    monkeypatch.setenv('MOBILE_QR_PHOTO_ONLY','true')
    try:
        spec=importlib.util.spec_from_file_location('gallery_mobile_isolation',scripts/'mobile_qr_demo.py')
        mobile=importlib.util.module_from_spec(spec);spec.loader.exec_module(mobile)
        with TestClient(create_public_app(settings)) as public:
            def get(url,**kwargs):
                response=public.get(url)
                return response.status_code,response.content,dict(response.headers)
            monkeypatch.setattr(mobile,'get',get)
            class Opener:
                def open(self,request,**kwargs):
                    response=public.request(request.get_method(),request.full_url)
                    assert response.status_code in (404,405)
                    raise mobile.HTTPError(request.full_url,response.status_code,'Denied',dict(response.headers),BytesIO(response.content))
            monkeypatch.setattr(mobile,'build_opener',lambda *args:Opener())
            mobile.denied('http://testserver',True)
            assert public.get('/gallery').status_code==200
            assert public.get('/gallery/api/photos').json()['items']==[]
    finally:sys.path.remove(str(scripts))
