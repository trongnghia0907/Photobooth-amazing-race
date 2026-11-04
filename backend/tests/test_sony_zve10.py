"""FAKE driver contracts only. No Sony USB, real shutter or hardware validation."""
from dataclasses import replace
import hashlib
import secrets
import time
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.services.camera.base import CameraCapabilities, CameraError, CapturedPhoto
from app.services.camera.mock import MockCameraAdapter
from app.services.camera.sony_zve10 import SonyZvE10CameraAdapter
from test_sessions import create, headers, key
from test_printing import login


class FakeSonyCommandDriver(MockCameraAdapter):
    """Synthetic images/receipts; these tests never execute Sony commands."""
    def __init__(self):
        super().__init__()
        self.model='ZV-E10';self.connects=0;self.disconnects=0;self.attempts=0
        self.missing=False;self.shutter_timeout=False;self.transfer_timeout=False
        self.preview_busy=False;self.bad_photo=False;self.originals={}

    def get_capabilities(self):
        return CameraCapabilities('sony_zve10','FAKE Sony driver, NO HARDWARE',False,True,True,True,True,'camera_original')

    def get_status(self):return {**super().get_status(),'model':self.model}

    def connect(self):
        self.connects+=1
        if self.missing:raise CameraError('disconnected','FAKE: camera unavailable.',stage='connect')
        super().connect()

    def disconnect(self):self.disconnects+=1;super().disconnect()

    def get_preview_frame(self):
        if self.preview_busy:
            self.preview_busy=False
            raise CameraError('busy','FAKE: shutter temporarily interrupts Live View.',stage='preview')
        return super().get_preview_frame()

    def capture_photo(self,capture_id,deadline):
        self.attempts+=1
        if self.shutter_timeout:raise TimeoutError('FAKE shutter timeout')
        return super().capture_photo(capture_id,deadline)

    def get_captured_photo(self,reference,deadline):
        if self.transfer_timeout:raise TimeoutError('FAKE transfer timeout')
        if self.bad_photo:return CapturedPhoto(b'not a JPEG','image/jpeg','camera_original')
        photo=super().get_captured_photo(reference,deadline)
        self.originals[reference]=photo.data
        return CapturedPhoto(photo.data,'image/jpeg','camera_original')


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path/'sony-fake',camera_adapter='sony_zve10',camera_guest_enabled=True,
                    app_env='development',admin_username='sony-test',admin_password=secrets.token_urlsafe(24))


def attached(settings):
    app=create_app(settings)
    driver=FakeSonyCommandDriver()
    return app,driver


def install_fake(app,driver):
    app.state.camera.adapter=SonyZvE10CameraAdapter(driver)


def connect(client,sid):
    base=f'/api/sessions/{sid}/camera'
    result=client.post(base+'/connect',headers=headers());assert result.status_code==200,result.text
    assert client.post(base+'/live-view/start',headers=headers()).status_code==200
    return base


def capture(client,base,slot,operation=None):
    return client.post(base+'/captures',headers=headers(operation or key()),json={'slot_index':slot})


def test_selectable_but_unimplemented_real_transport_fails_closed(settings):
    with TestClient(create_app(settings)) as client:
        sid=create(client);base=f'/api/sessions/{sid}/camera'
        state=client.get(base+'/status',headers=headers()).json()
        assert state['capabilities']['adapter']=='sony_zve10'
        assert not any(state['capabilities'][flag] for flag in ['demo','capture','live_view','physical_shutter','original_file','hardware_verified'])
        result=client.post(base+'/connect',headers=headers())
        assert result.status_code==503 and result.json()['error']['code']=='unsupported'
        assert 'No shutter' in result.json()['error']['message']
        assert client.get('/api/admin/camera').status_code==401
        csrf=login(client,settings)
        assert any(row['id']=='sony_zve10' for row in client.get('/api/admin/camera').json()['adapters'])
        assert client.put('/api/admin/camera/config',headers=csrf,json={'adapter':'mock'}).status_code==200
        assert client.put('/api/admin/camera/config',headers=csrf,json={'adapter':'sony_zve10'}).status_code==200
        with client.app.state.repository.db.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM camera_captures').fetchone()[0]==0


@pytest.mark.parametrize('count,layout',[(4,'landscape_4'),(6,'grid2x3')])
def test_fake_shutter_original_jpeg_slots_retake_and_replay(settings,count,layout):
    app,driver=attached(settings)
    with TestClient(app) as client:
        install_fake(app,driver);sid=create(client,slot_count=count,layout=layout);base=connect(client,sid)
        preview=client.get(base+'/frame',headers=headers());assert preview.status_code==200
        ids=[]
        for slot in range(count):
            operation=key();response=capture(client,base,slot,operation)
            assert response.status_code==200,response.text
            result=response.json();photo=result['session']['photos'][slot];ids.append(photo['id'])
            assert photo['slot_index']==slot and photo['source']=='camera_original'
            raw=client.get(base+'/captures/'+result['capture']['id']+'/original',headers=headers()).content
            assert raw==driver.originals[result['capture']['id']] and raw!=preview.content
            assert hashlib.sha256(raw).hexdigest()==result['capture']['native_sha256']
            assert capture(client,base,slot,operation).json()==result
        assert driver.attempts==count
        retake=capture(client,base,1).json()['session']['photos']
        assert retake[1]['id']!=ids[1]
        assert [photo['id'] for photo in retake if photo['slot_index']!=1]==[value for index,value in enumerate(ids) if index!=1]
        assert driver.attempts==count+1 and driver.connects==1
        assert not client.get(base+'/status',headers=headers()).json()['capabilities']['hardware_verified']


def test_fake_camera_missing_and_wrong_generation_cleanup():
    driver=FakeSonyCommandDriver();adapter=SonyZvE10CameraAdapter(driver);driver.missing=True
    with pytest.raises(CameraError,match='unavailable'):adapter.connect()
    assert not adapter.get_status()['connected'] and driver.disconnects==1
    driver.missing=False;driver.model='ZV-E10M2'
    with pytest.raises(CameraError,match='original Sony ZV-E10'):adapter.connect()
    assert not adapter.get_status()['connected'] and driver.disconnects==2


def test_fake_shutter_timeout_is_uncertain_and_never_retriggers_same_key(settings):
    app,driver=attached(settings)
    with TestClient(app) as client:
        install_fake(app,driver);sid=create(client);base=connect(client,sid);operation=key();driver.shutter_timeout=True
        failed=capture(client,base,0,operation)
        assert failed.status_code==504 and failed.json()['error']['uncertain']
        assert capture(client,base,0,operation).status_code==504
        assert driver.attempts==1
        assert client.get('/api/sessions/'+sid,headers=headers()).json()['photos']==[]


@pytest.mark.parametrize('failure',['transfer_timeout','bad_photo'])
def test_fake_transfer_retry_preserves_slot_and_does_not_refire(settings,failure):
    app,driver=attached(settings)
    with TestClient(app) as client:
        install_fake(app,driver);sid=create(client);base=connect(client,sid)
        original=capture(client,base,0).json()['session']['photos'][0]['id']
        setattr(driver,failure,True);operation=key();failed=capture(client,base,0,operation)
        assert failed.status_code in (503,504)
        assert client.get('/api/sessions/'+sid,headers=headers()).json()['photos'][0]['id']==original
        assert driver.attempts==2
        setattr(driver,failure,False);result=capture(client,base,0,operation)
        assert result.status_code==200 and driver.attempts==2
        assert result.json()['session']['photos'][0]['id']!=original


def test_fake_preview_interruption_reconnect_and_cleanup(settings):
    app,driver=attached(settings)
    with TestClient(app) as client:
        install_fake(app,driver);sid=create(client);base=connect(client,sid)
        assert client.get(base+'/frame',headers=headers()).status_code==200
        driver.preview_busy=True
        assert client.get(base+'/frame',headers=headers()).status_code==409
        assert client.get(base+'/frame',headers=headers()).status_code==200
        recovered=client.get(base+'/status',headers=headers()).json()
        assert recovered['state']=='previewing' and recovered['last_error'] is None
        assert driver.connects==1 and driver.connected
        assert capture(client,base,0).status_code==200
        assert client.post(base+'/disconnect',headers=headers()).status_code==200
        connect(client,sid);assert driver.connects==2
    assert not driver.connected and not driver.previewing


def test_fake_deadline_prevents_late_shutter_and_event_mode_stays_unverified(settings):
    driver=FakeSonyCommandDriver();adapter=SonyZvE10CameraAdapter(driver);adapter.connect()
    with pytest.raises(CameraError) as failure:adapter.capture_photo(key(),time.monotonic()-1)
    assert not failure.value.uncertain and driver.attempts==0
    from app.services.camera.controller import CameraController
    from app.services.repository import Repository
    production=replace(settings,app_env='production',operation_mode='event')
    controller=CameraController(Repository(production),adapter)
    with pytest.raises(CameraError,match='SDK'):controller.check_event_capabilities()
    adapter.disconnect()
