from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
import hashlib
import secrets
import threading
import time
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.config import Settings
from app.main import create_app
from app.services.camera.base import CameraCapabilities, CameraError
from app.services.camera.controller import CameraController
from test_sessions import create, headers, key, composite, upload
from test_printing import login, wait_job, enqueue


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path/'camera',public_base_url='http://localhost:8000',app_env='development',
                    camera_guest_enabled=True,camera_allow_faults=True,
                    admin_username='test-host',admin_password=secrets.token_urlsafe(24))


def connect(client,sid):
    base=f'/api/sessions/{sid}/camera'
    result=client.post(base+'/connect',headers=headers());assert result.status_code==200,result.text
    assert client.post(base+'/live-view/start',headers=headers()).status_code==200
    frame=client.get(base+'/frame',headers=headers());assert frame.status_code==200,frame.text
    return base


def capture(client,base,slot,operation=None):
    return client.post(base+'/captures',headers=headers(operation or key()),json={'slot_index':slot})


@pytest.mark.parametrize('count,layout',[(4,'landscape_4'),(6,'grid2x3')])
def test_host_camera_files_slots_retake_finalize_qr_print_host_restart(settings,count,layout):
    app=create_app(settings)
    with TestClient(app) as client:
        sid=create(client,slot_count=count,layout=layout);base=connect(client,sid)
        caps=client.get(base+'/status',headers=headers()).json()['capabilities']
        assert caps['demo'] and caps['capture'] and not caps['physical_shutter'] and not caps['original_file']
        photos=[]
        for slot in range(count):
            operation=key();response=capture(client,base,slot,operation);assert response.status_code==200,response.text
            result=response.json();assert result['capture']['status']=='captured'
            state=result['session'];assert len(state['photos'])==slot+1
            photo=state['photos'][slot];photos.append(photo['id'])
            assert photo['slot_index']==slot and (photo['width'],photo['height'])==(1600,1200)
            raw=client.get(base+f"/captures/{result['capture']['id']}/original",headers=headers()).content
            assert hashlib.sha256(raw).hexdigest()==result['capture']['native_sha256']
            assert Image.open(BytesIO(raw)).format=='JPEG'
            assert client.get(base+f"/captures/{result['capture']['id']}",headers=headers()).json()==result
            assert capture(client,base,slot,operation).json()==result
            assert capture(client,base,(slot+1)%count,operation).status_code==409
        assert app.state.camera.adapter.shutter_calls==count
        retake=capture(client,base,1).json();state=retake['session']
        assert state['photos'][1]['id']!=photos[1]
        assert [p['id'] for i,p in enumerate(state['photos']) if i!=1]==[p for i,p in enumerate(photos) if i!=1]
        assert len(list((settings.storage_root/'camera_originals'/sid).glob('*.jpg')))==count+1
        state=composite(client,sid,state['shots_revision']).json();cid=state['composite']['id']
        client.post(f'/api/sessions/{sid}/complete',headers=headers(key()),json={'composite_id':cid})
        final=client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json={'composite_id':cid}).json()
        guest_bytes=client.get(final['share']['download_url']).content
        job=enqueue(client,sid,final).json();assert wait_job(client,sid,job['id'])['status']=='submitted'
        assert client.post(base+'/disconnect',headers=headers()).status_code==200
        assert capture(client,base,count-1,operation).json()==result  # no camera needed to replay saved ACK
        login(client,settings)
        assert client.get(f'/api/admin/sessions/{sid}').json()['composites'][0]['print_ready_url']
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(final['share']['download_url']).content==guest_bytes
        assert capture(restarted,base,count-1,operation).json()==result
        assert restarted.app.state.camera.adapter.shutter_calls==0
        assert restarted.get(base+f"/captures/{result['capture']['id']}/original",headers=headers()).status_code==410
        assert not list((settings.storage_root/'camera_originals'/sid).glob('*.jpg'))


@pytest.mark.parametrize('failure',['timeout','capture','disconnect','transfer'])
def test_camera_failures_preserve_slot_and_retry_with_controlled_shutter(settings,failure):
    app=create_app(settings)
    with TestClient(app) as client:
        sid=create(client);base=connect(client,sid)
        original=capture(client,base,0).json()['capture']['photo_id']
        adapter=app.state.camera.adapter;adapter.failure=failure;operation=key()
        failed=capture(client,base,0,operation);assert failed.status_code in (503,504),failed.text
        assert client.get(f'/api/sessions/{sid}',headers=headers()).json()['photos'][0]['id']==original
        calls=adapter.shutter_calls
        if failure=='transfer':
            recovered=capture(client,base,0,operation)
            assert recovered.status_code==200,recovered.text
            assert adapter.shutter_calls==calls  # retry transfer, never another shutter
        else:
            assert capture(client,base,0,operation).status_code in (503,504)
            assert adapter.shutter_calls==calls
            connect(client,sid)
            assert capture(client,base,0).status_code==200  # explicit new shot/key only
            assert adapter.shutter_calls==calls+1


def test_live_stop_stale_reconnect_disconnect_and_lease_expiry(settings):
    app=create_app(settings)
    with TestClient(app) as client:
        sid=create(client);base=connect(client,sid)
        first=client.get(base+'/frame',headers=headers());second=client.get(base+'/frame',headers=headers())
        assert int(second.headers['x-frame-sequence'])>int(first.headers['x-frame-sequence'])
        assert client.get(base+'/status',headers=headers()).json()['preview_healthy']
        app.state.camera.adapter.failure='stale_preview'
        assert client.get(base+'/frame',headers=headers()).json()['error']['code']=='stale_preview'
        assert not client.get(base+'/status',headers=headers()).json()['preview_healthy']
        app.state.camera.adapter.failure=None;connect(client,sid)
        assert client.post(base+'/live-view/stop',headers=headers()).status_code==200
        assert client.get(base+'/frame',headers=headers()).status_code==503
        assert client.post(base+'/live-view/start',headers=headers()).status_code==200
        app.state.camera.lease_until=time.monotonic()-1
        status=client.get(base+'/status',headers=headers()).json()
        assert not status['connected'] and not status['lease_active']
        connect(client,sid);assert client.post(base+'/disconnect',headers=headers()).status_code==200
        assert client.get(base+'/frame',headers=headers()).status_code==409


def test_auth_admin_isolation_one_session_one_capture_and_stale_slot_conflict(settings,monkeypatch):
    app=create_app(settings)
    with TestClient(app) as client:
        sid=create(client);other=create(client);base=connect(client,sid)
        assert client.post(f'/api/sessions/{other}/camera/connect',headers=headers()).status_code==409
        assert client.get(base+'/frame').status_code==401
        assert client.get(base+'/status',headers=headers(token='b'*64)).status_code==404
        assert client.get('/api/admin/camera').status_code==401
        assert client.put('/api/admin/camera/config',json={'adapter':'mock'}).status_code==401
        original=app.state.camera.adapter.capture_photo;entered=threading.Event();release=threading.Event()
        def slow(cid,deadline):entered.set();assert release.wait(5);return original(cid,deadline)
        monkeypatch.setattr(app.state.camera.adapter,'capture_photo',slow)
        with ThreadPoolExecutor() as pool:
            first=pool.submit(capture,client,base,0)
            assert entered.wait(5)
            assert capture(client,base,1).json()['error']['code']=='busy'
            assert client.post(base+'/disconnect',headers=headers()).status_code==409
            # Another authorized photo mutation must not be overwritten by a
            # camera transfer that started against an earlier revision.
            assert upload(client,sid,0).status_code==200
            release.set();assert first.result().status_code==409
        session=client.get(f'/api/sessions/{sid}',headers=headers()).json()
        assert session['photos'][0]['source']=='demo' and session['photos'][0]['width']==80
        assert len(list((settings.storage_root/'camera_originals'/sid).glob('*.jpg')))==1
        assert client.get(f'/api/sessions/{other}/camera/captures/{key()}',headers=headers()).status_code==404
        client.post(base+'/disconnect',headers=headers());csrf=login(client,settings)
        assert client.put('/api/admin/camera/config',json={'guest_enabled':False}).status_code==403
        assert client.put('/api/admin/camera/config',headers=csrf,json={'guest_enabled':False}).status_code==200
        assert client.post(base+'/connect',headers=headers()).status_code==409
        assert client.put('/api/admin/camera/config',headers=csrf,json={'guest_enabled':True,'adapter':'vendor'}).status_code==200
        assert client.post(base+'/connect',headers=headers()).json()['error']['code']=='unsupported'
        diagnostic=client.get('/api/admin/camera').json()
        assert not diagnostic['capabilities']['capture'] and diagnostic['blocked_by_hardware']


def test_capture_restart_reconciles_uncertain_shutter_but_resumes_transfer(settings):
    app=create_app(settings)
    with TestClient(app) as client:
        sid=create(client);base=connect(client,sid);adapter=app.state.camera.adapter
        adapter.failure='transfer';operation=key();assert capture(client,base,0,operation).status_code==503
        with app.state.repository.db.connect() as db:
            db.execute("UPDATE camera_captures SET status='transferring'")
    with TestClient(create_app(settings)) as client:
        connect(client,sid);result=capture(client,base,0,operation);assert result.status_code==200,result.text
        assert client.app.state.camera.adapter.shutter_calls==0
        operation=key()
        with client.app.state.repository.db.connect() as db:
            db.execute("INSERT INTO camera_captures(id,session_id,request_key,slot_index,expected_revision,adapter_mode,status,created_at,updated_at) VALUES (?,?,?,?,?,'mock','capturing','now','now')",(key(),sid,operation,1,1))
    with TestClient(create_app(settings)) as client:
        result=capture(client,base,1,operation)
        assert result.status_code==503 and result.json()['error']['uncertain']
        assert client.app.state.camera.adapter.shutter_calls==0


def test_mock_faults_protected_native_paths_and_input_only_commands(settings):
    app=create_app(settings)
    with TestClient(app) as client:
        sid=create(client);base=connect(client,sid)
        assert client.post(base+'/captures',headers=headers(key()),json={'slot_index':0,'image':'pretend preview screenshot'}).status_code==422
        assert capture(client,base,6).status_code==422
        assert capture(client,base,True).status_code==422
        csrf=login(client,settings)
        assert client.post('/api/admin/camera/mock-failure',headers=csrf,json={'failure':'transfer'}).status_code==200
        assert capture(client,base,0).status_code==503
        assert client.get('/runtime/camera_originals').status_code==404
        assert client.get(base+'/captures/../../photobooth.sqlite3/original',headers=headers()).status_code in (404,422)


def test_controller_os_lock_prevents_other_process_owner(settings):
    app=create_app(settings)
    with TestClient(app) as client:
        sid=create(client);connect(client,sid)
        other=CameraController(app.state.repository)
        try:
            with pytest.raises(CameraError,match='process khác'):other.connect(sid,'a'*64)
        finally:other.stop()


def test_real_adapter_contract_preserves_native_file_without_preview_substitution(settings,monkeypatch):
    from app.services.camera.base import CapturedPhoto
    app=create_app(settings)
    with TestClient(app) as client:
        service=app.state.camera;adapter=service.adapter
        original_get=adapter.get_captured_photo
        monkeypatch.setattr(adapter,'get_capabilities',lambda:CameraCapabilities('test_sdk','Fake SDK contract (no hardware)',False,True,True,True,True,'camera_original'))
        def transferred(reference,deadline):
            photo=original_get(reference,deadline)
            return CapturedPhoto(photo.data,photo.mime,'camera_original')
        monkeypatch.setattr(adapter,'get_captured_photo',transferred)
        sid=create(client);base=connect(client,sid);result=capture(client,base,0)
        assert result.status_code==200,result.text
        assert result.json()['session']['photos'][0]['source']=='camera_original'
        assert not client.get(base+'/status',headers=headers()).json()['capabilities']['hardware_verified']
        monkeypatch.setattr(adapter,'get_capabilities',lambda:CameraCapabilities('bad_sdk','Unsupported',False,True,True,False,False,'unsupported'))
        calls=adapter.shutter_calls
        assert capture(client,base,1).status_code==503
        assert adapter.shutter_calls==calls


def test_optional_uvc_adapter_uses_driver_frames_and_reports_demo_only(settings,monkeypatch):
    import sys
    from types import SimpleNamespace
    from app.services.camera.uvc_demo import UvcDemoCameraAdapter
    calls=[]
    class Device:
        def isOpened(self):return True
        def read(self):calls.append('frame');return True,object()
        def release(self):calls.append('release')
    class Encoded:
        def tobytes(self):return b'fake-driver-jpeg'
    monkeypatch.setitem(sys.modules,'cv2',SimpleNamespace(VideoCapture=lambda *args:Device(),CAP_DSHOW=700,CAP_ANY=0,imencode=lambda *args:(True,Encoded())))
    adapter=UvcDemoCameraAdapter(settings.storage_root)
    adapter.connect();adapter.start_live_view();assert adapter.get_preview_frame().data==b'fake-driver-jpeg'
    reference=adapter.capture_photo(key(),time.monotonic()+5)
    captured=adapter.get_captured_photo(reference,time.monotonic()+5)
    assert captured.source=='webcam_frame'
    assert not adapter.get_capabilities().physical_shutter and not adapter.get_capabilities().original_file
    adapter.disconnect();assert calls==['frame','frame','release']
