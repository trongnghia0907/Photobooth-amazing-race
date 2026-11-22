"""Bounded locks, capture stages and second-shot failure; no physical camera."""
from concurrent.futures import ThreadPoolExecutor
from ctypes import c_int32
from dataclasses import replace
import json
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.camera.base import CameraError
from app.services.camera.sony_wia import WindowsWiaTransport, _check
from app.services.camera import sony_ptp as ptp
from test_sony_consecutive import StatefulWia
from test_sony_ptp import FakeWia
from test_sony_zve10 import settings, connect, capture
from test_sessions import create, headers, key


class MissingSecondJpeg(StatefulWia):
    def _exchange(self, opcode, params=(), **kwargs):
        result=super()._exchange(opcode,params,**kwargs)
        if opcode==0x9207 and params==(ptp.SHUTTER_RELEASE,) and kwargs.get('data')==b'\2\0' and self.shots==2:
            self.photos.clear()  # ACK is independent of a completed exposure.
        return result


def test_second_ack_without_jpeg_preserves_first_and_same_intent_retry(settings,caplog):
    settings=replace(settings,camera_timeout_seconds=1)
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;wire=MissingSecondJpeg();camera.adapter.driver.transport=wire
        sid=create(client);base=connect(client,sid)
        first=capture(client,base,0).json();first_id=first['capture']['id']
        first_bytes=client.get(base+'/captures/'+first_id+'/original',headers=headers()).content
        operation=key();failed=capture(client,base,1,operation)
        assert failed.status_code==504 and failed.json()['error']['uncertain']
        assert failed.json()['error']['shutter_dispatched'] is True
        cid=failed.json()['error']['capture_id']
        progress=client.get(base+'/status',headers=headers(operation)).json()['capture_progress']
        assert progress['shutter_acknowledged'] and not progress['jpeg_validated'] and not progress['jpeg_saved']
        status=client.get(base+'/status',headers=headers()).json()
        assert status['state']=='error' and status['connected'] is True
        assert status['capture_progress']['stage']=='error'
        assert status['camera_progress']['stage']=='waiting_buffer'
        assert status['camera_progress']['last_buffer_value']==0
        assert status['camera_progress']['buffer_polls']>0
        assert 'receiving_original' in status['capture_progress']['timings_ms']
        assert f'sony_buffer_wait_failed capture_id={cid}' in caplog.text
        assert 'last_file_info=0 code=timeout connected=True' in caplog.text
        def retry():
            return client.post(base+'/captures',headers=headers(operation),json={'slot_index':1,'recovery_only':True})
        assert retry().status_code==504
        assert capture(client,base,2).status_code!=200 and wire.shots==2
        assert client.get(base+'/captures/'+first_id+'/original',headers=headers()).content==first_bytes
        # The same still-owned intent may recover its delayed original only.
        wire.photos.append((wire.originals[1],2))
        recovered=retry()
        assert recovered.status_code==200,recovered.text
        assert recovered.json()['capture']['id']==cid and wire.shots==2
        assert [p['slot_index'] for p in recovered.json()['session']['photos']]==[0,1]


def test_wia_disconnect_while_waiting_for_second_jpeg_reports_disconnected(settings,caplog):
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera
        wire=MissingSecondJpeg()
        camera.adapter.driver.transport=wire
        sid=create(client);base=connect(client,sid)
        first=capture(client,base,0).json()['capture']['id']
        exchange=wire._exchange

        def unplug(opcode,params=(),**kwargs):
            if opcode==0x9209 and wire.shots==2 and not wire.half and not wire.full:
                raise CameraError('disconnected','TEST WIA connection interrupted')
            return exchange(opcode,params,**kwargs)

        wire._exchange=unplug
        response=capture(client,base,1,key())
        assert response.status_code==503
        error=response.json()['error']
        assert (error['code'],error['stage'],error['uncertain'])==('disconnected','transfer',True)
        status=client.get(base+'/status',headers=headers()).json()
        assert status['state']=='disconnected' and status['connected'] is False
        assert 'code=disconnected connected=False' in caplog.text
        assert wire.shots==2
        photo=client.get(base+'/captures/'+first+'/original',headers=headers())
        assert photo.content==wire.originals[0]


def test_camera_io_wait_obeys_deadline_and_does_not_send_a_shutter(settings):
    settings=replace(settings,camera_timeout_seconds=1)
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;wire=StatefulWia();camera.adapter.driver.transport=wire
        sid=create(client);base=connect(client,sid);operation=key()
        camera.io.acquire();start=time.perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(capture,client,base,0,operation)
                result=future.result(timeout=3)
            elapsed=time.perf_counter()-start
            assert result.status_code==409,result.text
            assert result.json()['error']['uncertain'] is False
            assert 0.8<=elapsed<2.5 and wire.shots==0
            assert not camera.adapter.driver.unresolved
        finally:camera.io.release()
        # No durable shutter intent existed during the lock timeout.
        assert capture(client,base,0,operation).status_code==200
        assert wire.shots==1


def test_waiting_camera_does_not_block_health_status_or_progress(settings):
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;wire=StatefulWia();device=camera.adapter.driver;device.transport=wire
        sid=create(client);base=connect(client,sid)
        entered=threading.Event();resume=threading.Event();command=wire.command
        def stalled(opcode,params=(),**kwargs):
            if opcode==0x9209 and wire.shots==1 and not wire.full and not wire.half and wire.photos:
                entered.set();assert resume.wait(4)
            return command(opcode,params,**kwargs)
        wire.command=stalled
        operation=key()
        with ThreadPoolExecutor(max_workers=1) as pool:
            request=pool.submit(capture,client,base,0,operation)
            try:
                assert entered.wait(2)
                started=time.perf_counter()
                health=client.get('/api/health');status=client.get(base+'/status',headers=headers(operation))
                elapsed=time.perf_counter()-started
                assert health.status_code==status.status_code==200
                assert status.json()['busy'] is True
                assert status.json()['capture_progress']['shutter_acknowledged'] is True
                assert status.json()['capture_progress']['jpeg_validated'] is False
                unrelated=client.get(base+'/status',headers=headers(key())).json()
                assert 'shutter_acknowledged' not in unrelated['capture_progress']
                assert status.json()['camera_progress']['stage']=='waiting_buffer'
                assert elapsed<1 and not request.done()
                assert client.get(base+'/frame',headers=headers()).status_code==409
            finally:resume.set()
            result=request.result(timeout=4)
            assert result.status_code==200,result.text
        assert camera.capture_progress['stage']=='complete'
        progress=client.get(base+'/status',headers=headers(operation)).json()['capture_progress']
        assert progress['shutter_acknowledged'] and progress['jpeg_validated'] and progress['jpeg_saved']
        assert {'shutter','receiving_original','normalizing','saving_original','saving_slot'}<=camera.capture_progress['timings_ms'].keys()


def test_still_alive_wia_worker_is_retained_and_cannot_be_replaced(monkeypatch):
    class Process:
        alive=True;closed=False
        def is_alive(self):return self.alive
        def terminate(self):pass  # Model unsuccessful bounded cleanup.
        def join(self,timeout):assert timeout<=1
        def close(self):self.closed=True
    class Channel:
        closed=False
        def close(self):self.closed=True
    transport=WindowsWiaTransport();process=Process();channel=Channel()
    transport.process=process;transport.channel=channel
    with pytest.raises(CameraError,match='did not exit') as caught:transport.close(force=True)
    assert caught.value.code=='worker_stalled' and caught.value.uncertain
    assert transport.stalled_process is process and channel.closed and not process.closed
    # This must fail BEFORE creating another multiprocessing worker.
    with pytest.raises(CameraError,match='has not exited'):transport.open(time.monotonic()+1)
    with pytest.raises(CameraError,match='has not exited'):transport.close()
    assert transport.stalled_process is process
    process.alive=False
    monkeypatch.setattr('app.services.camera.sony_wia.mp.get_context',lambda *_:(_ for _ in ()).throw(RuntimeError('STOP before spawn')))
    with pytest.raises(RuntimeError,match='before spawn'):transport.open(time.monotonic()+1)
    assert process.closed and transport.stalled_process is None


@pytest.mark.parametrize(('hresult','code'),[
    (0x8000ffff,'transport_failed'),(0x8007001f,'transport_failed'),(0x8021000e,'transport_failed'),
    (0x80210006,'busy'),(None,'not_ready'),
])
def test_preview_only_replaces_an_invalid_wia_root(settings,hresult,code):
    class RootCheckingWia(FakeWia):
        def open(self,deadline):
            assert not self.connected, 'opening while the old root is active'
            super().open(deadline)
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;wire=RootCheckingWia();camera.adapter.driver.transport=wire
        sid=create(client);base=connect(client,sid)
        assert client.post(base+'/connect',headers=headers()).status_code==200
        assert wire.open_count==1
        command=wire.command
        def failed_read(opcode,*args,**kwargs):
            if opcode==0x9209 and hresult is not None:_check(c_int32(hresult).value,'IWiaItemExtras.Escape(PTP 0x9209)')
            return command(opcode,*args,**kwargs)
        wire.command=failed_read
        if hresult is None:wire.live=0
        result=client.get(base+'/frame',headers=headers())
        assert result.json()['error']['code']==code
        stale=code=='transport_failed'
        status=client.get(base+'/status',headers=headers()).json()
        assert status['connected'] is not stale and status['owned_by_session']
        assert wire.closed==int(stale) and wire.open_count==1
        assert client.post(f'/api/sessions/{create(client)}/camera/connect',headers=headers()).status_code==409
        wire.command=command;wire.live=1
        connect(client,sid)
        assert client.get(base+'/frame',headers=headers()).status_code==200
        assert wire.open_count==1+int(stale) and wire.shots==0


def test_full_press_dispatch_and_ack_are_distinct_when_release_fails(settings):
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;wire=StatefulWia();camera.adapter.driver.transport=wire
        sid=create(client);base=connect(client,sid);operation=key()
        entered=threading.Event();resume=threading.Event();command=wire.command
        wire.release_fault=(ptp.SHUTTER_RELEASE,1)
        def full_press(opcode,params=(),**kwargs):
            if opcode==0x9207 and params==(ptp.SHUTTER_RELEASE,) and kwargs.get('data')==b'\2\0':
                entered.set();assert resume.wait(4)
            return command(opcode,params,**kwargs)
        wire.command=full_press
        with ThreadPoolExecutor(max_workers=1) as pool:
            request=pool.submit(capture,client,base,0,operation)
            try:
                assert entered.wait(2)
                status=client.get(base+'/status',headers=headers(operation)).json()
                assert status['camera_progress']['stage']=='shutter_dispatch'
                assert not status['capture_progress']['shutter_acknowledged']
            finally:resume.set()
            error=request.result(timeout=3).json()['error']
        assert error['code']=='busy' and error['shutter_dispatched'] and error['uncertain']
        progress=client.get(base+'/status',headers=headers(operation)).json()['capture_progress']
        assert progress['shutter_acknowledged'] and not progress['jpeg_validated'] and not progress['jpeg_saved']
        assert capture(client,base,0,operation).status_code==200
        assert wire.shots==1
