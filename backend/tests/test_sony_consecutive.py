"""Stateful simulated WIA only; no hardware, production files or real sleeps."""
import hashlib
import json
import struct
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from pathlib import Path
import secrets

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageOps
from app.main import create_app
from app.services.camera import sony_ptp as ptp
from app.services.camera.base import CameraError
from test_sony_ptp import FakeWia, jpeg, props_dataset
from test_sony_zve10 import settings, connect, capture
from test_sessions import create, headers, key


class ProtocolClock:
    def __init__(self):self.value=time.monotonic()
    def monotonic(self):return self.value
    def sleep(self,seconds):self.value+=seconds
    def __getattr__(self,name):return getattr(time,name)


@pytest.fixture
def clock(monkeypatch):
    clock=ProtocolClock();monkeypatch.setattr(ptp,'time',clock);return clock


class StatefulWia(FakeWia):
    """ACKs, button state, transfer and delayed buffer drain are independent.

    Delays are deterministic property polls, not a claim about Sony timing.
    A second press is rejected while buttons or the previous buffer are busy.
    """
    def __init__(self):
        super().__init__()
        self.half=self.full=False;self.draining=0;self.hold_buffer=False
        self.focus_mode=1;self.focus_polls=0;self.focus_after=2
        self.release_fault=None;self.transfer_fault=False;self.originals=[]
        self.drain_error=None
        self.stale_descriptor=False;self.ack_without_release=False
        self.transfer_entered=self.transfer_resume=None
        self.in_command=False;self.ready_reported=True;self.preview_calls=0

    def command(self,opcode,params=(),**kwargs):
        assert not self.in_command,'Concurrent WIA access'
        self.in_command=True
        try:return self._exchange(opcode,params,**kwargs)
        finally:self.in_command=False

    def _exchange(self,opcode,params=(),**kwargs):
        if opcode==0x9207:
            code=params[0];value=struct.unpack('<H',kwargs['data'])[0]
            if self.ack_without_release and code==ptp.HALF_RELEASE and value==1:
                return super().command(opcode,params,**kwargs)  # ACK, but no completed exposure/image.
            if self.release_fault==(code,value):
                self.release_fault=None
                raise CameraError('busy','TEST release ACK unavailable')
            if code==ptp.HALF_RELEASE:
                if value==2:
                    assert not self.half and not self.full and not self.photos and not self.draining
                    assert self.ready_reported,'Buffer not confirmed empty after previous transfer'
                    self.focus_polls=0
                else:assert not self.full,'Full press must be released first'
                self.half=value==2
            elif code==ptp.SHUTTER_RELEASE:
                if value==2:
                    assert self.half and not self.full and not self.photos and not self.draining
                self.full=value==2
            else:pytest.fail('New captures must not use RequestOneShooting')
            result=super().command(opcode,params,**kwargs)
            if code==ptp.SHUTTER_RELEASE and value==2:
                original=jpeg((self.shots*31%255,self.shots*67%255,100))
                self.photos[-1]=(original,self.shots);self.originals.append(original)
            return result
        if opcode==0x9209:
            if self.draining and self.drain_error:
                error=self.drain_error;self.drain_error=None
                raise CameraError(error,'TEST post-transfer property failure')
            super().command(opcode,params,**kwargs)  # Exercise the WIA codec too.
            if self.half and self.full:self.focus_polls+=1
            count=0x8001 if self.photos else 0
            if self.half or self.full:count=0
            if self.draining:
                count=0x8001
                if not self.hold_buffer:self.draining-=1
            if count==0 and not self.half and not self.full:self.ready_reported=True
            return props_dataset({ptp.FILE_INFO:count,ptp.LIVE_STATUS:1,
                ptp.SAVE_DESTINATION:self.destination,0x5004:self.compression,0x5013:self.drive,
                ptp.FOCUS_MODE:self.focus_mode,
                ptp.HALF_RELEASE:2 if self.half or self.stale_descriptor else 1,
                ptp.SHUTTER_RELEASE:2 if self.full or self.stale_descriptor else 1,
                ptp.FOCUS_FOUND:2 if self.focus_polls>=self.focus_after else 1})
        if opcode==0x1009 and params==(ptp.SHOT,):
            assert not self.half and not self.full,'Transfer started with shutter held'
            if self.transfer_entered:
                self.transfer_entered.set();assert self.transfer_resume.wait(3)
            if self.transfer_fault:
                self.transfer_fault=False
                raise CameraError('usb','TEST interrupted before complete JPEG')
            result=super().command(opcode,params,**kwargs)
            self.draining=3;self.ready_reported=False
            return result
        if opcode==0x1009 and params==(ptp.LIVE,):self.preview_calls+=1
        return super().command(opcode,params,**kwargs)


def driver(tmp_path):
    wire=StatefulWia();camera=ptp.SonyPtpDriver(tmp_path,transport=wire)
    camera.connect();return camera,wire


@pytest.mark.parametrize('count',[2,4,6])
@pytest.mark.parametrize('stale_descriptor',[False,True])
def test_consecutive_originals_wait_for_release_durable_cache_and_buffer_drain(tmp_path,clock,count,monkeypatch,stale_descriptor):
    camera,wire=driver(tmp_path)
    wire.stale_descriptor=stale_descriptor
    identifiers=[]
    def verify_drain(journal,record,deadline):
        saved=camera._paths(journal.stem)[1]
        assert saved.read_bytes()==wire.originals[-1]
        assert record['received_sha256']==hashlib.sha256(saved.read_bytes()).hexdigest()
        assert not record['release_pending'] and not record['half_release_pending']
        return wait(journal,record,deadline)
    wait=camera._wait_buffer_drained;monkeypatch.setattr(camera,'_wait_buffer_drained',verify_drain)
    for index in range(count):
        identifier=str(uuid.uuid4());identifiers.append(identifier);deadline=clock.monotonic()+5
        camera.capture_photo(identifier,deadline)
        assert camera.get_captured_photo(identifier,deadline).data==wire.originals[index]
        record=json.loads(camera._paths(identifier)[0].read_text())
        assert record['buffer_drained'] and record['last_buffer_value']==0
        assert wire.ready_reported and not wire.half and not wire.full and not wire.draining
        before=wire.shots;camera.capture_photo(identifier,deadline)
        assert wire.shots==before  # Duplicate intent never presses again.
    assert wire.shots==count and wire.open_count==1 and not camera.unresolved
    assert len({hashlib.sha256(data).digest() for data in wire.originals})==count
    for identifier,original in zip(identifiers,wire.originals):
        assert camera._paths(identifier)[1].read_bytes()==original


@pytest.mark.parametrize('count',[4,6])
def test_host_consecutive_slots_keep_exact_originals(settings,clock,count):
    with TestClient(create_app(settings)) as client:
        wire=StatefulWia();camera=client.app.state.camera;camera.adapter.driver.transport=wire
        sid=create(client,layout='landscape_4' if count==4 else 'grid2x3',slot_count=count)
        base=connect(client,sid)
        for slot in range(count):
            operation=key();result=capture(client,base,slot,operation)
            assert result.status_code==200,result.text
            cid=result.json()['capture']['id'];assert result.json()['capture']['slot_index']==slot
            with client.app.state.repository.db.connect() as db:
                row=db.execute('SELECT native_path,native_sha256 FROM camera_captures WHERE id=?',(cid,)).fetchone()
            assert (settings.storage_root/row['native_path']).read_bytes()==wire.originals[slot]
            assert row['native_sha256']==hashlib.sha256(wire.originals[slot]).hexdigest()
            assert capture(client,base,slot,operation).json()==result.json()
        assert wire.shots==count and wire.open_count==1 and wire.ready_reported


def test_buffer_timeout_keeps_original_and_retries_after_restart_without_retransfer(tmp_path,clock):
    camera,wire=driver(tmp_path);identifier=str(uuid.uuid4());wire.hold_buffer=True
    camera.capture_photo(identifier,clock.monotonic()+5)
    with pytest.raises(CameraError,match='readiness is unverified'):
        camera.get_captured_photo(identifier,clock.monotonic()+0.5)
    journal,saved=camera._paths(identifier);original=saved.read_bytes()
    record=json.loads(journal.read_text());assert record['status']=='dispatched'
    assert record['received_sha256']==hashlib.sha256(original).hexdigest()
    with pytest.raises(CameraError,match='previous Sony capture'):
        camera.capture_photo(str(uuid.uuid4()),clock.monotonic()+5)
    before=sum(op==0x1009 and params==(ptp.SHOT,) for op,params,_ in wire.commands)
    camera.disconnect();camera=ptp.SonyPtpDriver(tmp_path,transport=wire);camera.connect()
    wire.hold_buffer=False
    assert camera.get_captured_photo(identifier,clock.monotonic()+5).data==original
    assert sum(op==0x1009 and params==(ptp.SHOT,) for op,params,_ in wire.commands)==before
    next_id=str(uuid.uuid4());camera.capture_photo(next_id,clock.monotonic()+5)
    assert camera.get_captured_photo(next_id,clock.monotonic()+5).data!=original
    assert wire.shots==2 and saved.read_bytes()==original


def test_interrupted_unknown_transfer_blocks_next_shutter_and_preserves_buffer(tmp_path,clock):
    camera,wire=driver(tmp_path);identifier=str(uuid.uuid4())
    camera.capture_photo(identifier,clock.monotonic()+5);original=wire.originals[0];wire.transfer_fault=True
    with pytest.raises(CameraError,match='interrupted'):camera.get_captured_photo(identifier,clock.monotonic()+5)
    for _ in range(2):
        with pytest.raises(CameraError) as error:camera.get_captured_photo(identifier,clock.monotonic()+5)
        assert error.value.code=='recovery_required'
        with pytest.raises(CameraError):camera.capture_photo(str(uuid.uuid4()),clock.monotonic()+5)
    assert wire.shots==1 and wire.photos[0][0]==original and not wire.half and not wire.full


@pytest.mark.parametrize('control',[ptp.SHUTTER_RELEASE,ptp.HALF_RELEASE])
def test_release_retry_never_repeats_press(tmp_path,clock,control):
    camera,wire=driver(tmp_path);identifier=str(uuid.uuid4());wire.release_fault=(control,1)
    with pytest.raises(CameraError,match='release ACK'):camera.capture_photo(identifier,clock.monotonic()+5)
    assert wire.shots==1
    with pytest.raises(CameraError):camera.capture_photo(str(uuid.uuid4()),clock.monotonic()+5)
    before=len(wire.commands)
    camera.recover_capture(identifier,clock.monotonic()+5)
    assert all(data==b'\1\0' for op,_,data in wire.commands[before:] if op==0x9207)
    assert camera.get_captured_photo(identifier,clock.monotonic()+5).data==wire.originals[0]
    assert wire.shots==1 and not wire.half and not wire.full


@pytest.mark.parametrize('focus_after',[2,100])
def test_af_wait_is_bounded_and_both_buttons_are_released(tmp_path,clock,focus_after):
    camera,wire=driver(tmp_path);wire.focus_mode=2;wire.focus_after=focus_after
    identifier=str(uuid.uuid4());start=clock.monotonic()
    camera.capture_photo(identifier,start+5)
    assert 0<clock.monotonic()-start<1.2
    assert not wire.full and not wire.half
    assert camera.get_captured_photo(identifier,clock.monotonic()+5).data==wire.originals[0]


def test_preview_and_second_capture_cannot_enter_wia_during_transfer(settings,clock):
    with TestClient(create_app(settings)) as client:
        wire=StatefulWia();client.app.state.camera.adapter.driver.transport=wire
        sid=create(client);base=connect(client,sid)
        assert client.get(base+'/frame',headers=headers()).status_code==200
        wire.transfer_entered=threading.Event();wire.transfer_resume=threading.Event()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(capture,client,base,0)
            try:
                assert wire.transfer_entered.wait(2)
                previews=wire.preview_calls
                assert client.get(base+'/frame',headers=headers()).status_code==409
                assert capture(client,base,1).status_code==409
                assert wire.preview_calls==previews and wire.shots==1
            finally:wire.transfer_resume.set()
            assert future.result(timeout=3).status_code==200
        wire.transfer_entered=None
        assert client.get(base+'/frame',headers=headers()).status_code==200
        assert capture(client,base,1).status_code==200
        assert wire.shots==2 and wire.open_count==1


@pytest.mark.parametrize('error',['busy','disconnected'])
def test_post_transfer_busy_or_disconnect_preserves_checksum_bound_original(tmp_path,clock,error):
    camera,wire=driver(tmp_path);identifier=str(uuid.uuid4())
    camera.capture_photo(identifier,clock.monotonic()+5);wire.drain_error=error
    if error=='disconnected':
        with pytest.raises(CameraError):camera.get_captured_photo(identifier,clock.monotonic()+5)
        saved=camera._paths(identifier)[1];assert saved.read_bytes()==wire.originals[0]
        camera.connect()
    assert camera.get_captured_photo(identifier,clock.monotonic()+5).data==wire.originals[0]
    assert wire.shots==1 and not camera.unresolved and wire.ready_reported
    assert sum(op==0x1009 and params==(ptp.SHOT,) for op,params,_ in wire.commands)==1


def test_lost_shutter_ack_reconnect_releases_only_and_never_rebinds_unknown_buffer(tmp_path,clock):
    camera,wire=driver(tmp_path);identifier=str(uuid.uuid4());wire.fault='shutter_timeout'
    with pytest.raises(CameraError):camera.capture_photo(identifier,clock.monotonic()+5)
    assert wire.shots==1 and wire.half and wire.full
    camera.connect();before=len(wire.commands)
    camera.recover_capture(identifier,clock.monotonic()+5)
    assert [(params,data) for op,params,data in wire.commands[before:] if op==0x9207]==[
        ((ptp.SHUTTER_RELEASE,),b'\1\0'),((ptp.HALF_RELEASE,),b'\1\0')]
    with pytest.raises(CameraError) as error:camera.get_captured_photo(identifier,clock.monotonic()+5)
    assert error.value.code=='recovery_required'
    with pytest.raises(CameraError):camera.capture_photo(str(uuid.uuid4()),clock.monotonic()+5)
    assert wire.shots==1 and wire.photos and not camera._paths(identifier)[1].exists()


@pytest.mark.parametrize('control',[ptp.SHUTTER_RELEASE,ptp.HALF_RELEASE])
def test_button_descriptor_does_not_replace_original_completion_evidence(tmp_path,clock,control):
    wire=FakeWia();wire.button_states[control]=2
    camera=ptp.SonyPtpDriver(tmp_path,transport=wire);camera.connect()
    identifier=str(uuid.uuid4());camera.capture_photo(identifier,clock.monotonic()+5)
    # Neither a descriptor value nor the release ACK can complete an intent.
    with pytest.raises(CameraError,match='previous Sony capture'):
        camera.capture_photo(str(uuid.uuid4()),clock.monotonic()+5)
    assert wire.shots==1
    assert camera.get_captured_photo(identifier,clock.monotonic()+5).data
    assert not camera.unresolved


def test_stale_control_readback_does_not_block_a_verified_saved_original(tmp_path,clock,monkeypatch):
    camera,wire=driver(tmp_path);identifier=str(uuid.uuid4())
    camera.capture_photo(identifier,clock.monotonic()+5)
    command=wire.command
    def held_readback(opcode,params=(),**kwargs):
        data=command(opcode,params,**kwargs)
        if opcode==0x9209:
            props=ptp.property_info(data)
            values={code:prop['value'] for code,prop in props.items()}
            values[ptp.SHUTTER_RELEASE]=2
            return props_dataset(values)
        return data
    monkeypatch.setattr(wire,'command',held_readback)
    assert camera.get_captured_photo(identifier,clock.monotonic()+5).data==wire.originals[0]
    journal,saved=camera._paths(identifier)
    assert saved.read_bytes()==wire.originals[0]
    record=json.loads(journal.read_text())
    assert record['status']=='saved' and record['buffer_drained'] and wire.shots==1


def test_release_ack_without_completed_exposure_does_not_allow_next_shutter(tmp_path,clock):
    camera,wire=driver(tmp_path);identifier=str(uuid.uuid4());wire.ack_without_release=True
    camera.capture_photo(identifier,clock.monotonic()+5)
    with pytest.raises(CameraError) as error:camera.get_captured_photo(identifier,clock.monotonic()+0.5)
    assert error.value.uncertain and error.value.stage=='transfer'
    journal,saved=camera._paths(identifier);record=json.loads(journal.read_text())
    assert record['status']=='dispatched' and record['object'] is None and not saved.exists()
    assert not record['release_pending'] and not record['half_release_pending']
    assert wire.half and wire.shots==1
    for _ in range(2):
        with pytest.raises(CameraError):camera.capture_photo(str(uuid.uuid4()),clock.monotonic()+5)
    assert wire.shots==1


def test_unacknowledged_release_still_blocks_buffer_completion(tmp_path,clock):
    camera,wire=driver(tmp_path);identifier=str(uuid.uuid4())
    record={'status':'dispatched','object':None,'release_pending':True}
    journal,_=camera._paths(identifier);camera._record(journal,record)
    before=len(wire.commands)
    with pytest.raises(CameraError,match='release is unconfirmed'):
        camera._wait_buffer_drained(journal,record,clock.monotonic()+5)
    assert len(wire.commands)==before and wire.shots==0


def test_host_reports_no_jpeg_after_ack_as_uncertain_without_retrying(settings,clock):
    settings=replace(settings,camera_timeout_seconds=1)
    with TestClient(create_app(settings)) as client:
        wire=StatefulWia();wire.ack_without_release=True
        client.app.state.camera.adapter.driver.transport=wire
        sid=create(client);base=connect(client,sid)
        response=capture(client,base,0)
        assert response.status_code==504,response.text
        error=response.json()['error']
        assert error['uncertain'] is True and error['stage']=='transfer'
        with client.app.state.repository.db.connect() as db:
            row=db.execute('SELECT status,uncertain,native_path FROM camera_captures WHERE id=?',(error['capture_id'],)).fetchone()
        assert row['status']=='transfer_failed' and row['uncertain']==1 and row['native_path'] is None
        assert capture(client,base,1).status_code!=200 and wire.shots==1


@pytest.mark.parametrize('count',[4,6])
def test_simulated_sony_originals_complete_one_composite_and_one_published_item(settings,clock,count):
    settings=replace(settings,frontend_dist=Path(__file__).resolve().parents[2]/'frontend/dist-host',
        booth_pairing_key=secrets.token_urlsafe(24))
    with TestClient(create_app(settings),base_url='http://localhost:8000',client=('127.0.0.1',123)) as client:
        assert client.get('/api/booth/recent-photos').status_code==401
        paired=client.post('/api/booth/pair',headers={'X-OSA-Pair':'1'},json={'key':settings.booth_pairing_key})
        assert paired.status_code==200,paired.text
        client.headers['X-Booth-CSRF']=paired.json()['csrf_token']
        wire=StatefulWia();client.app.state.camera.adapter.driver.transport=wire
        sid=create(client,layout='landscape_4' if count==4 else 'grid2x3',slot_count=count)
        base=connect(client,sid);retained=[]
        backup=settings.storage_root/'acceptance_originals';backup.mkdir()
        for slot in range(count):
            response=capture(client,base,slot);assert response.status_code==200,response.text
            state=response.json()['session'];cid=response.json()['capture']['id']
            raw=client.get(base+'/captures/'+cid+'/original',headers=headers())
            assert raw.status_code==200 and raw.content==wire.originals[slot]
            path=backup/(cid+'.jpg');path.write_bytes(raw.content);retained.append(path)
        size=(720,480) if count==4 else (480,720)
        canvas=Image.new('RGB',size,'navy');cell=(size[0]//2,size[1]//(count//2))
        for slot,data in enumerate(wire.originals):
            with Image.open(BytesIO(data)) as original:
                thumb=ImageOps.contain(ImageOps.exif_transpose(original),cell)
                canvas.paste(thumb,((slot%2)*cell[0]+(cell[0]-thumb.width)//2,
                    (slot//2)*cell[1]+(cell[1]-thumb.height)//2))
        payload=BytesIO();canvas.save(payload,'PNG')
        response=client.put(f'/api/sessions/{sid}/composite',headers=headers(key()),
            data={'shots_revision':state['shots_revision'],'editor_json':json.dumps({'event_display_consent':True})},
            files={'file':('final.png',payload.getvalue(),'image/png')})
        assert response.status_code==200,response.text
        composite_id=response.json()['composite']['id'];operation=key();body={'composite_id':composite_id}
        response=client.post(f'/api/sessions/{sid}/complete',headers=headers(operation),json=body)
        assert response.status_code==200,response.text
        assert response.json()['status']=='completed'
        assert client.post(f'/api/sessions/{sid}/complete',headers=headers(operation),json=body).json()==response.json()
        feed=client.get('/api/booth/recent-photos',headers=headers())
        assert feed.status_code==200,feed.text
        items=feed.json()['items'];assert len(items)==1
        displayed=client.get(items[0]['image_url'],headers=headers());assert displayed.status_code==200
        with Image.open(BytesIO(displayed.content)) as image:
            image.load();assert (image.width>image.height)==(count==4)
        with client.app.state.repository.db.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM composites WHERE session_id=?',(sid,)).fetchone()[0]==1
        assert wire.shots==count and wire.open_count==1
        for path,original in zip(retained,wire.originals):
            assert path.read_bytes()==original
