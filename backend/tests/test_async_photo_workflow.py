from dataclasses import replace
from io import BytesIO
import threading,time,hashlib,json
import pytest,zxingcpp,httpx
from PIL import Image
from fastapi.testclient import TestClient
from app.public_main import create_public_app
from app.event_display import EventDisplay,approved_photo_feed
from test_drive_storage import setup,confirmed,finalize
from test_sessions import key,headers,create,upload,image

def consented(client):
    sid=create(client,layout='grid2x3',slot_count=6)
    for slot in range(6):state=upload(client,sid,slot).json()
    r=client.put('/api/sessions/'+sid+'/composite',headers=headers(key()),data={'shots_revision':state['shots_revision'],'editor_json':'{"event_display_consent":true}'},files={'file':('final.png',image('blue',(800,1200)),'image/png')})
    cid=r.json()['composite']['id']
    assert client.post('/api/sessions/'+sid+'/complete',headers=headers(key()),json={'composite_id':cid}).status_code==200
    return sid,cid

def test_qr_and_local_public_photo_do_not_wait_for_background_upload(setup,monkeypatch):
    client,repo,fake,settings=setup
    repo.settings=replace(settings,event_gallery_auto_publish=True)
    sid,cid=consented(client)
    entered=threading.Event();release=threading.Event();upload=fake.upload
    def slow_upload(*args):entered.set();assert release.wait(10);return upload(*args)
    fake.upload=slow_upload;worker=threading.Thread(target=repo.drive.process_one);worker.start();assert entered.wait(2)
    try:
        start=time.perf_counter();state=finalize(client,sid,cid).json();qr_ms=(time.perf_counter()-start)*1000
        assert state['share'] and worker.is_alive() and not repo.drive.ready(cid)
        share=state['share'];token=share['share_url'].rsplit('/',1)[1]
        feed=approved_photo_feed(EventDisplay(repo),100,'/event-display/media')
        assert len(feed['items'])==1 and not repo.drive.ready(cid)
        with TestClient(create_public_app(settings)) as public:
            public.app.state.repository.drive.client=fake
            public_repo=public.app.state.repository
            public_repo.drive.local=lambda *_:pytest.fail('Local staged photos must not call Drive')
            status=public.get('/p/'+token+'/status');assert status.json()['registered']
            class Probe:
                def __init__(self,**kwargs):pass
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def get(self,url):return public.get('/p/'+token+'/status')
            monkeypatch.setattr(httpx,'Client',Probe)
            probe_started=time.perf_counter();verified=repo.sharing.verify_public(sid,'a'*64)
            print(f'GATEWAY_REGISTRATION_MOCK_MS={(time.perf_counter()-probe_started)*1000:.1f}')
            assert verified['public_ready'] and not repo.drive.ready(cid)
            data=public.get(share['download_url']).content
            assert public.get(share['image_url']).content==data
            assert zxingcpp.read_barcode(Image.open(BytesIO(data))).text==share['share_url']
            assert public.get('/admin').status_code==404
            # The same worker cannot claim the same in-flight job again.
            assert repo.drive.process_one() is False
            with repo.db.connect() as db:
                assert db.execute('SELECT COUNT(*) FROM session_finals').fetchone()[0]==1
                assert db.execute('SELECT COUNT(*) FROM drive_uploads').fetchone()[0]==1
            print(f'QR_WHILE_UPLOAD_BLOCKED_MS={qr_ms:.1f}')
    finally:release.set();worker.join(5)
    assert repo.drive.ready(cid) and len(fake.files)==1
    assert finalize(client,sid,cid).json()['share']['share_url']==share['share_url']

def test_pending_page_recovers_without_changing_token_and_offline_upload_keeps_staging(setup):
    client,repo,fake,settings=setup;sid,cid=confirmed(client,4)
    state=finalize(client,sid,cid).json();share=state['share'];token=share['share_url'].rsplit('/',1)[1]
    path=settings.storage_root/f'composites/{sid}/{cid}.png';saved=path.with_suffix('.test-held');path.rename(saved)
    with TestClient(create_public_app(settings)) as public:
        public.app.state.repository.drive.client=fake
        assert public.get('/p/'+token+'/status').json()['registered']
        page=public.get('/p/'+token);assert page.status_code==202 and 'Ảnh đang được xử lý' in page.text and 'setTimeout' in page.text
        assert 'guestDownload' not in page.text
        saved.rename(path)
        fake.offline=True;repo.drive.process_one();assert path.is_file() and not repo.drive.ready(cid)
        assert public.get('/p/'+token).status_code==200
        fake.offline=False;repo.drive.retry();repo.drive.process_one();assert repo.drive.ready(cid)
        assert public.get('/p/'+token).status_code==200
        assert public.get(share['download_url']).status_code==200
        assert finalize(client,sid,cid).json()['share']['share_url']==share['share_url']

def test_gateway_unavailable_never_verifies_public_qr(setup,monkeypatch):
    client,repo,fake,settings=setup;sid,cid=confirmed(client);finalize(client,sid,cid)
    class Offline:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url):raise httpx.ConnectError('offline')
    monkeypatch.setattr(httpx,'Client',Offline)
    response=client.get('/api/sessions/'+sid+'/public-status',headers=headers())
    assert response.status_code==503
    assert not repo.get(sid,'a'*64)['share']['public_ready']
