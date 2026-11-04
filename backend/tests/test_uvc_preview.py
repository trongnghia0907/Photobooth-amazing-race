"""Real UVC adapter with fake frame sources; never opens a physical webcam."""
from io import BytesIO
import sys
import threading
import time
from types import SimpleNamespace
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.services.camera.base import CameraError
from app.services.camera.uvc_demo import UvcDemoCameraAdapter
from test_sessions import create, headers, key


class Frame:
    shape=(1200,1600,3)
    def __init__(self,width=1600,height=1200):self.shape=(height,width,3)


class FakeCv:
    CAP_DSHOW=700;CAP_ANY=0;CAP_PROP_BUFFERSIZE=38;CAP_PROP_FPS=5;IMWRITE_JPEG_QUALITY=1
    def __init__(self):
        self.devices=[];self.encodings=[];self.failures=0;self.closed=False
        self.block=threading.Event();self.block.set()
        self.read_entered=threading.Event();self.encode_fail=False

    def VideoCapture(self,*args):
        source=self
        class Device:
            opened=True
            def __init__(self):self.calls=[];self.releases=[];self.properties=[]
            def isOpened(self):return self.opened and not source.closed
            def set(self,prop,value):self.properties.append((prop,value));return True
            def read(self):
                self.calls.append(threading.get_ident());source.read_entered.set()
                assert source.block.wait(8),'Fake read was not released by test'
                if source.failures:
                    source.failures-=1;return False,None
                return True,Frame()
            def release(self):self.releases.append(threading.get_ident());self.opened=False
        device=Device();self.devices.append(device);return device

    def resize(self,frame,size):return Frame(*size)

    def imencode(self,extension,frame,params=None):
        if self.encode_fail and params:return False,None
        height,width=frame.shape[:2]
        self.encodings.append((width,height,params))
        buffer=BytesIO();Image.new('RGB',(width,height),'blue').save(buffer,'JPEG',quality=params[1] if params else 95)
        return True,SimpleNamespace(tobytes=lambda:buffer.getvalue())


@pytest.fixture
def webcam(tmp_path,monkeypatch):
    source=FakeCv();monkeypatch.setitem(sys.modules,'cv2',source)
    adapter=UvcDemoCameraAdapter(tmp_path)
    yield adapter,source
    source.block.set();adapter.disconnect()


def wait_preview(adapter,sequence=-1):
    with adapter.condition:
        assert adapter.condition.wait_for(lambda:adapter.preview is not None and adapter.preview.sequence>sequence,3)
    return adapter.get_preview_frame()


def test_preview_is_small_capture_is_native_one_owner_and_cleanup(webcam):
    adapter,source=webcam;adapter.connect();adapter.start_live_view()
    preview=wait_preview(adapter)
    with Image.open(BytesIO(preview.data)) as image:assert image.size==(960,720)
    reference=adapter.capture_photo(key(),time.monotonic()+3)
    native=adapter.get_captured_photo(reference,time.monotonic()+3)
    with Image.open(BytesIO(native.data)) as image:assert image.size==(1600,1200)
    assert native.source=='webcam_frame' and not adapter.get_capabilities().physical_shutter
    assert adapter.capture_photo(reference,time.monotonic()+3)==reference
    assert len([row for row in source.encodings if row[2] is None])==1
    stats=adapter.get_status()['preview_diagnostics']
    assert stats['read_ms']>=0 and stats['encode_ms']>=0 and stats['opens']==1
    adapter.disconnect()
    device=source.devices[0]
    assert len(source.devices)==1 and len(device.releases)==1
    assert set(device.calls)==set(device.releases)  # Same owning thread releases it.
    assert not adapter.thread.is_alive()


def test_one_failed_read_recovers_without_reopening(webcam):
    adapter,source=webcam;source.failures=1
    adapter.connect();adapter.start_live_view();assert wait_preview(adapter).data
    assert adapter.connected and len(source.devices)==1
    stats=adapter.get_status()['preview_diagnostics']
    assert stats['read_failures']==1 and stats['consecutive_read_failures']==0


def test_repeated_failures_stop_once_and_allow_explicit_reconnect(webcam):
    adapter,source=webcam;source.failures=5
    adapter.connect();adapter.thread.join(3)
    assert not adapter.thread.is_alive() and not adapter.connected
    with pytest.raises(CameraError) as caught:adapter.get_preview_frame()
    assert caught.value.code=='camera_read_failed'  # Not asserted as physical USB loss.
    assert adapter.get_status()['preview_diagnostics']['consecutive_read_failures']==5
    adapter.connect();adapter.start_live_view();assert wait_preview(adapter).data
    assert len(source.devices)==2 and len(source.devices[0].releases)==1


def test_blocked_native_read_does_not_block_http_buffer_or_create_second_owner(webcam):
    adapter,source=webcam;source.block.clear()
    adapter.connect();adapter.start_live_view();assert source.read_entered.wait(1)
    started=time.monotonic()
    with pytest.raises(CameraError) as caught:adapter.get_preview_frame()
    assert caught.value.code=='preview_pending' and time.monotonic()-started<0.5
    with pytest.raises(CameraError,match='did not deliver'):adapter.capture_photo(key(),time.monotonic()+0.05)
    assert adapter.get_status()['preview_diagnostics']['read_in_progress_ms']>=40
    adapter.disconnect()
    with pytest.raises(CameraError) as caught:adapter.connect()
    assert caught.value.code=='worker_stalled' and len(source.devices)==1
    replacement=UvcDemoCameraAdapter(adapter.root)
    with pytest.raises(CameraError) as caught:replacement.connect()
    assert caught.value.code=='worker_stalled' and len(source.devices)==1
    source.block.set();adapter.thread.join(2)
    assert len(source.devices[0].releases)==1


def test_preview_encode_failure_does_not_disconnect_or_break_native_capture(webcam):
    adapter,source=webcam;source.encode_fail=True
    adapter.connect();adapter.start_live_view()
    with adapter.condition:
        assert adapter.condition.wait_for(lambda:adapter.metrics['encode_failures']>0,2)
    assert adapter.connected
    receipt=adapter.capture_photo(key(),time.monotonic()+2)
    assert adapter.get_captured_photo(receipt,time.monotonic()+1).data
    source.encode_fail=False;assert wait_preview(adapter).data


@pytest.mark.parametrize('mode,app_env,allowed',[('development','development',False),('rehearsal','production',True)])
@pytest.mark.parametrize('count,layout',[(4,'landscape_4'),(6,'grid2x3')])
def test_uvc_api_capture_retake_replay_and_allowed_modes(tmp_path,monkeypatch,mode,app_env,allowed,count,layout):
    source=FakeCv();monkeypatch.setitem(sys.modules,'cv2',source)
    settings=Settings(tmp_path/'host',camera_adapter='uvc_demo',camera_guest_enabled=True,
                      app_env=app_env,operation_mode=mode,allow_mock_hardware=allowed)
    with TestClient(create_app(settings)) as client:
        sid=create(client,slot_count=count,layout=layout);base=f'/api/sessions/{sid}/camera'
        assert client.post(base+'/connect',headers=headers()).status_code==200
        assert client.post(base+'/live-view/start',headers=headers()).status_code==200
        adapter=client.app.state.camera.adapter;wait_preview(adapter)
        wait_preview(adapter,adapter.delivered)
        # API must not do another native read while serving the buffered JPEG.
        with adapter.condition:adapter.delivered=-1
        response=client.get(base+'/frame',headers=headers());assert response.status_code==200
        assert float(response.headers['X-Preview-Processing-Ms'])>=0
        ids=[]
        for slot in range(count):
            operation=key();data={'slot_index':slot}
            response=client.post(base+'/captures',headers=headers(operation),json=data)
            assert response.status_code==200,response.text
            result=response.json();ids.append(result['session']['photos'][slot]['id'])
            assert result['session']['photos'][slot]['width']==1600
            assert client.post(base+'/captures',headers=headers(operation),json=data).json()==result
        result=client.post(base+'/captures',headers=headers(key()),json={'slot_index':1}).json()
        assert result['session']['photos'][1]['id']!=ids[1]
        assert [p['id'] for p in result['session']['photos'] if p['slot_index']!=1]==[p for i,p in enumerate(ids) if i!=1]
        assert len([row for row in source.encodings if row[2] is None])==count+1
        assert len(source.devices)==1


@pytest.mark.parametrize('mode',['event','development'])
def test_production_without_explicit_rehearsal_still_rejects_uvc(tmp_path,mode):
    settings=Settings(tmp_path,camera_adapter='uvc_demo',app_env='production',operation_mode=mode)
    with pytest.raises(CameraError) as caught:
        with TestClient(create_app(settings)):pass
    assert caught.value.code=='demo_only'
