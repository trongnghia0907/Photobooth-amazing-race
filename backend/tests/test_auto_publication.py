import json
from dataclasses import replace
from fastapi.testclient import TestClient
import pytest
from app.main import create_app
from app.public_main import create_public_app
from test_sessions import create,upload,headers,key,image
from test_event_display import login,enable,approve
from test_printing import settings

@pytest.mark.parametrize('auto,consent,expected',[(False,True,0),(True,False,0),(True,'true',0),(True,True,1)])
def test_auto_publication_requires_host_policy_and_explicit_guest_consent(settings,auto,consent,expected):
    settings=replace(settings,event_gallery_auto_publish=auto)
    with TestClient(create_app(settings)) as client:
        sid=create(client,layout='landscape_4',slot_count=4)
        for slot in range(4):state=upload(client,sid,slot).json()
        r=client.put(f'/api/sessions/{sid}/composite',headers=headers(key()),data={'shots_revision':state['shots_revision'],'editor_json':json.dumps({'event_display_consent':consent})},files={'file':('final.png',image('green'),'image/png')})
        assert r.status_code==200
        cid=r.json()['composite']['id'];body={'composite_id':cid}
        assert client.post(f'/api/sessions/{sid}/complete',headers=headers(key()),json=body).status_code==200
        csrf=login(client,settings);enable(client,csrf)
        feed=client.get('/event-display/api/photos').json()['items'];assert len(feed)==expected
        assert client.post(f'/api/sessions/{sid}/complete',headers=headers(key()),json=body).status_code==200
        assert client.get('/event-display/api/photos').json()['items']==feed
        if not auto and consent is True:
            client.app.state.repository.settings=replace(settings,event_gallery_auto_publish=True)
            assert client.post(f'/api/sessions/{sid}/complete',headers=headers(key()),json=body).status_code==200
            assert client.get('/event-display/api/photos').json()['items']==[]
        if expected:
            assert client.put('/api/admin/event-display/photos/'+sid,headers=csrf,json={'approved':False}).status_code==200
            assert client.post(f'/api/sessions/{sid}/complete',headers=headers(key()),json=body).status_code==200
            assert client.get('/event-display/api/photos').json()['items']==[]

def test_auto_publish_default_and_explicit_host_disable(tmp_path,monkeypatch):
    from app.config import Settings
    monkeypatch.setenv('APP_ENV','development');monkeypatch.setenv('OPERATION_MODE','development')
    monkeypatch.setenv('OSA_STORAGE_ROOT',str(tmp_path))
    monkeypatch.delenv('EVENT_GALLERY_AUTO_PUBLISH',raising=False)
    assert Settings.from_environment().event_gallery_auto_publish is True
    monkeypatch.setenv('EVENT_GALLERY_AUTO_PUBLISH','false')
    assert Settings.from_environment().event_gallery_auto_publish is False

def test_disposable_gateway_blocks_other_valid_sessions(settings,monkeypatch):
    from test_sharing import finalized
    from urllib.parse import urlsplit
    with TestClient(create_app(settings)) as private:
        sid,_,a=finalized(private,'green');_,_,b=finalized(private,'blue')
    monkeypatch.setenv('MOBILE_QR_TEST_SESSION_ID',sid)
    with TestClient(create_public_app(settings)) as public:
        probe=public.get('/p/invalid')
        assert probe.status_code==404 and 'AMAZING RACE 2026' in probe.text
        first=urlsplit(a['share']['share_url']).path;other=urlsplit(b['share']['share_url']).path
        for suffix in ['', '/image','/download','/qr.png']:
            assert public.get(first+suffix).status_code==200
            assert public.get(other+suffix).status_code==404
        for path in ['/admin','/api/admin/sessions','/api/camera/status','/api/admin/print-jobs','/event-display']:
            assert public.get(path).status_code==404
