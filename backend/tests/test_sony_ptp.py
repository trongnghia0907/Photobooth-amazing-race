"""Sony production protocol + synthetic WIA wire fixtures; NO physical camera.

Fixtures encode the documented PTP 2 datasets, not captured vendor/private data.
The fake boundary is WIA/USB; all Sony parsing, capture and recovery are real code.
"""
from io import BytesIO
from pathlib import Path
import struct
import time
import uuid
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.camera.base import CameraError
from app.services.camera.sony_ptp import (SonyPtpDriver, Reader, device_info, object_info,
    property_info, SHOT, LIVE, ONE_SHOT, FILE_INFO, LIVE_STATUS, SAVE_DESTINATION)
from app.services.camera.sony_wia import (encode_command, decode_response, IN_HEADER,
    OUT_HEADER, WindowsWiaTransport, _Spec, _Variant)
from app.services.camera.sony_zve10 import SonyZvE10CameraAdapter
from test_sessions import create, headers, key


def string(value):
    return bytes([len(value)+1])+value.encode('utf-16-le')+b'\0\0'


def array(values):return struct.pack('<I',len(values))+struct.pack('<'+'H'*len(values),*values)


def jpeg(color):
    buf=BytesIO();exif=Image.Exif();exif[274]=6
    Image.new('RGB',(320,240),color).save(buf,'JPEG',exif=exif)
    return buf.getvalue()


def object_dataset(data, sequence=0, name='DSC00001.JPG'):
    return struct.pack('<IHHIHIIIIIIIHI I'.replace(' ',''),
        1,0x3801,0,len(data),0,0,0,0,320,240,24,0,0,0,sequence)+string(name)+string('')*3


PROPS=[FILE_INFO,LIVE_STATUS,SAVE_DESTINATION,0x5004,0x5013]
OPS=[0x1001,0x1008,0x1009,0x9201,0x9202,0x9207,0x9209]


def device_dataset(model='ZV-E10'):
    return (struct.pack('<HIH',100,17,100)+string('Sony')+b'\0\0'+array(OPS)+array([0xc201])+
            array(PROPS)+array([0x3801])*2+string('Sony Corporation')+string(model)+string('2.00')+string('NOT-EXPOSED'))


def props_dataset(values, enum_lists=0):
    result=struct.pack('<Q',len(values))
    for code,value in values.items():
        width=1 if code in (LIVE_STATUS,0x5004) else 2
        result+=struct.pack('<HHBB',code,2 if width==1 else 4,0,1)+bytes(width)+value.to_bytes(width,'little')
        if enum_lists:
            result+=b'\2'+(struct.pack('<H',1)+value.to_bytes(width,'little'))*enum_lists
        else:result+=b'\1'+bytes(width*2)+b'\1'+bytes(width-1)
    return result


class FakeWia:
    def __init__(self):
        self.model='ZV-E10';self.connected=False;self.open_count=0;self.closed=0
        self.preview=jpeg('blue');self.photos=[];self.shots=0;self.commands=[]
        self.fault=None;self.live=1;self.drive=1;self.compression=3;self.destination=0x11
        self.properties=PROPS;self.controls=[ONE_SHOT];self.version=0xc8

    def open(self,deadline):self.connected=True;self.open_count+=1
    def close(self):self.connected=False;self.closed+=1

    def command(self,opcode,params=(),*,data=None,limit=65536,deadline):
        assert time.monotonic()<deadline
        packet=encode_command(opcode,params,data)
        fields=IN_HEADER.unpack_from(packet)
        assert fields[:3]==(opcode,0,0)  # WIA owns IDs, not the app.
        assert fields[-2:]==(len(params),3 if data is None else 4)
        self.commands.append((opcode,params,data))
        result=b'';code=0x2001
        if opcode==0x1001:result=device_dataset(self.model)
        elif opcode==0x9201:result=bytes(8)
        elif opcode==0x9202:result=struct.pack('<H',self.version)+array(self.properties)+array(self.controls)
        elif opcode==0x9209:
            values={FILE_INFO:0x8001 if self.photos else 0,LIVE_STATUS:self.live,
                    SAVE_DESTINATION:self.destination,0x5004:self.compression,0x5013:self.drive}
            result=props_dataset(values)
        elif opcode==0x9207:
            assert params==(ONE_SHOT,)
            value=struct.unpack('<H',data)[0]
            if value==2:
                self.shots+=1;self.photos.append((jpeg('red' if self.shots%2 else 'green'),self.shots))
                if self.fault=='shutter_timeout':
                    self.fault=None;raise CameraError('timeout','FAKE lost shutter response')
            else:assert value==1
        elif opcode==0x1008:
            if params==(LIVE,):result=object_dataset(b'0'*8+self.preview)
            elif self.photos:
                photo,seq=self.photos[0];result=object_dataset(photo,seq,f'DSC{seq:05}.JPG')
            else:code=0x2009
        elif opcode==0x1009:
            if params==(LIVE,):
                result=struct.pack('<II',8,len(self.preview))+self.preview
                if self.fault=='bad_preview':result=struct.pack('<II',999999,40)+b'bad'
            else:
                if self.fault=='transfer_timeout':
                    self.fault=None;raise CameraError('timeout','FAKE transfer timeout')
                result,seq=self.photos[0]
                if self.fault=='bad_jpeg':self.fault=None;result=b'X'*len(result)
                else:self.photos.pop(0)
        else:pytest.fail(f'Undocumented/unexpected operation {opcode:#x}')
        return decode_response(OUT_HEADER.pack(code,9,len(self.commands),*([0]*5))+result,limit)


def driver(tmp_path):
    wire=FakeWia();real=SonyPtpDriver(tmp_path,transport=wire)
    real.connect();return real,wire


def test_wia_codec_layout_and_driver_owned_ids():
    assert IN_HEADER.size==38 and OUT_HEADER.size==30
    packet=encode_command(0x9207,(ONE_SHOT,),b'\2\0')
    assert packet[:10]==b'\7\x92'+bytes(8)
    assert struct.unpack_from('<II',packet,30)==(1,4)
    assert packet[38:]==b'\2\0'
    assert decode_response(OUT_HEADER.pack(0x2001,10,999,0,0,0,0,0)+b'123',3)==b'123'
    with pytest.raises(ValueError):encode_command(0x9207,(1,)*6)
    with pytest.raises(CameraError):decode_response(b'',3)
    with pytest.raises(CameraError):decode_response(OUT_HEADER.pack(0x2001,0,0,0,0,0,0,0)+b'123',2)


@pytest.mark.parametrize('code,kind',[(0x2019,'busy'),(0x2003,'disconnected'),(0x2005,'unsupported'),(0x200f,'not_ready'),(0x2002,'protocol')])
def test_wia_error_codes(code,kind):
    with pytest.raises(CameraError) as caught:decode_response(OUT_HEADER.pack(code,0,0,0,0,0,0,0),0)
    assert caught.value.code==kind


@pytest.mark.parametrize('lists',[0,1,2])
def test_real_property_parser_accepts_documented_forms(lists):
    props=property_info(props_dataset({FILE_INFO:0x8001,LIVE_STATUS:1},lists))
    assert props[FILE_INFO]['value']==0x8001 and props[LIVE_STATUS]['value']==1


@pytest.mark.parametrize('data',[b'',b'\xff'*64,struct.pack('<Q',99999),props_dataset({FILE_INFO:0})[:-1]])
def test_invalid_property_datasets_fail_closed(data):
    with pytest.raises(CameraError):property_info(data)


def test_identity_and_initialization(tmp_path):
    real,wire=driver(tmp_path)
    assert wire.commands[:5]==[(0x1001,(),None),(0x9201,(1,0,0),None),(0x9201,(2,0,0),None),
        (0x9202,(0xc8,),None),(0x9201,(3,0,0),None)]
    assert real.get_status()['model']=='ZV-E10' and real.get_capabilities().hardware_verified is False
    assert 'NOT-EXPOSED' not in str(device_info(device_dataset()))
    real.disconnect();assert wire.closed==1 and not real.connected


@pytest.mark.parametrize('model',['ZV-E10M2','ILCE-7M4'])
def test_other_models_rejected_before_initialization(tmp_path,model):
    wire=FakeWia();wire.model=model;real=SonyPtpDriver(tmp_path,transport=wire)
    with pytest.raises(CameraError,match='original Sony ZV-E10'):real.connect()
    assert wire.closed==1 and wire.shots==0
    assert [c[0] for c in wire.commands]==[0x1001]


@pytest.mark.parametrize('attribute,value',[('properties',[]),('controls',[]),('version',0x12c)])
def test_incompatible_profile_rejected(tmp_path,attribute,value):
    wire=FakeWia();setattr(wire,attribute,value)
    real=SonyPtpDriver(tmp_path,transport=wire)
    with pytest.raises(CameraError,match='required ZV-E10 PTP 2'):real.connect()
    assert wire.closed==1 and wire.shots==0


def test_preview_is_framed_decoded_and_not_a_still_capture(tmp_path):
    real,wire=driver(tmp_path);real.start_live_view()
    first=real.get_preview_frame();second=real.get_preview_frame()
    assert first.data==wire.preview and second.sequence==first.sequence+1
    assert wire.shots==0
    assert len([c for c in wire.commands if c[:2]==(0x1008,(LIVE,))])==1
    wire.fault='bad_preview'
    with pytest.raises(CameraError):real.get_preview_frame()
    assert real.connected
    wire.fault=None;wire.live=0
    with pytest.raises(CameraError,match='temporarily unavailable'):real.get_preview_frame()
    wire.live=1;assert real.get_preview_frame().data==wire.preview and wire.open_count==1


@pytest.mark.parametrize('attribute,value',[('drive',2),('compression',0x13),('destination',0x10)])
def test_capture_preflight_does_not_change_camera_settings_or_fire(tmp_path,attribute,value):
    real,wire=driver(tmp_path);setattr(wire,attribute,value)
    with pytest.raises(CameraError):real.capture_photo(str(uuid.uuid4()),time.monotonic()+1)
    assert wire.shots==0 and not list(real.root.glob('*.json'))


def test_original_transfer_and_receipt_survive_driver_restart(tmp_path):
    real,wire=driver(tmp_path);identifier=str(uuid.uuid4());end=time.monotonic()+2
    reference=real.capture_photo(identifier,end);original=wire.photos[0][0]
    assert wire.commands[-2:]==[(0x9207,(ONE_SHOT,),b'\2\0'),(0x9207,(ONE_SHOT,),b'\1\0')]
    photo=real.get_captured_photo(reference,end)
    assert photo.data==original and photo.data!=wire.preview and photo.source=='camera_original'
    with Image.open(BytesIO(photo.data)) as image:assert image.size==(320,240) and image.getexif()[274]==6
    real.disconnect();again=SonyPtpDriver(tmp_path,transport=wire);again.connect()
    assert again.capture_photo(identifier,end)==reference
    assert again.get_captured_photo(reference,end).data==original and wire.shots==1


@pytest.mark.parametrize('fault',['transfer_timeout','bad_jpeg'])
def test_transfer_retry_never_refires_shutter(tmp_path,fault):
    real,wire=driver(tmp_path);identifier=str(uuid.uuid4());end=time.monotonic()+3
    reference=real.capture_photo(identifier,end);wire.fault=fault
    with pytest.raises(CameraError):real.get_captured_photo(reference,end)
    if not real.connected:real.connect()
    assert real.get_captured_photo(reference,end).mime=='image/jpeg' and wire.shots==1


def test_uncertain_shutter_reconciles_without_another_shutter(tmp_path):
    real,wire=driver(tmp_path);identifier=str(uuid.uuid4());end=time.monotonic()+3
    wire.fault='shutter_timeout'
    with pytest.raises(CameraError) as caught:real.capture_photo(identifier,end)
    assert caught.value.uncertain and wire.shots==1
    real.connect()
    with pytest.raises(CameraError,match='previous Sony capture'):real.capture_photo(str(uuid.uuid4()),end)
    reference=real.recover_capture(identifier,end)
    assert real.get_captured_photo(reference,end).data!=wire.preview and wire.shots==1


def test_changed_camera_buffer_is_not_assigned_to_old_capture(tmp_path):
    real,wire=driver(tmp_path);end=time.monotonic()+2
    reference=real.capture_photo(str(uuid.uuid4()),end);wire.fault='bad_jpeg'
    with pytest.raises(CameraError):real.get_captured_photo(reference,end)
    wire.photos=[(jpeg('yellow'),999)]
    with pytest.raises(CameraError,match='buffer changed'):real.get_captured_photo(reference,end)
    assert wire.shots==1


@pytest.mark.parametrize('count,layout',[(4,'landscape_4'),(6,'grid2x3')])
def test_real_driver_host_api_slots_retake_replay_and_originals(tmp_path,count,layout):
    from app.config import Settings
    settings=Settings(tmp_path/'host',camera_adapter='sony_zve10',camera_guest_enabled=True)
    app=create_app(settings);wire=FakeWia()
    with TestClient(app) as client:
        app.state.camera.adapter.driver.transport=wire
        sid=create(client,slot_count=count,layout=layout);base=f'/api/sessions/{sid}/camera'
        assert client.post(base+'/connect',headers=headers()).status_code==200
        assert client.post(base+'/live-view/start',headers=headers()).status_code==200
        assert client.get(base+'/frame',headers=headers()).content==wire.preview
        ids=[]
        for slot in range(count):
            operation=key();payload={'slot_index':slot}
            response=client.post(base+'/captures',headers=headers(operation),json=payload)
            assert response.status_code==200,response.text
            result=response.json();ids.append(result['session']['photos'][slot]['id'])
            assert result['session']['photos'][slot]['slot_index']==slot
            assert result['session']['photos'][slot]['source']=='camera_original'
            raw=client.get(base+'/captures/'+result['capture']['id']+'/original',headers=headers())
            assert raw.status_code==200 and raw.content!=wire.preview
            assert client.post(base+'/captures',headers=headers(operation),json=payload).json()==result
        retake=client.post(base+'/captures',headers=headers(key()),json={'slot_index':1}).json()
        assert retake['session']['photos'][1]['id']!=ids[1]
        assert [p['id'] for p in retake['session']['photos'] if p['slot_index']!=1]==[n for i,n in enumerate(ids) if i!=1]
        assert wire.shots==count+1 and wire.open_count==1


def test_host_api_recovers_lost_shutter_response_with_same_key(tmp_path):
    from app.config import Settings
    settings=Settings(tmp_path/'host',camera_adapter='sony_zve10',camera_guest_enabled=True)
    app=create_app(settings);wire=FakeWia()
    with TestClient(app) as client:
        app.state.camera.adapter.driver.transport=wire
        sid=create(client);base=f'/api/sessions/{sid}/camera'
        assert client.post(base+'/connect',headers=headers()).status_code==200
        wire.fault='shutter_timeout';operation=key()
        response=client.post(base+'/captures',headers=headers(operation),json={'slot_index':0})
        assert response.status_code==504 and response.json()['error']['uncertain']
        assert client.post(base+'/connect',headers=headers()).status_code==200
        response=client.post(base+'/captures',headers=headers(operation),json={'slot_index':0})
        assert response.status_code==200,response.text
        assert wire.shots==1 and response.json()['capture']['status']=='captured'


def test_wia_timeout_closes_only_its_owned_process(monkeypatch):
    class Channel:
        def send(self,item):pass
        def poll(self,timeout):return False
        def close(self):self.closed=True
    class Process:
        alive=True;terminated=False
        def is_alive(self):return self.alive
        def terminate(self):self.terminated=True;self.alive=False
        def join(self,timeout):assert timeout<=1
        def close(self):pass
    transport=WindowsWiaTransport();channel=Channel();process=Process()
    transport.channel,transport.process=channel,process
    with pytest.raises(CameraError,match='timed out'):
        transport.command(0x9209,deadline=time.monotonic()+0.02)
    assert process.terminated and channel.closed and transport.process is None


def test_missing_hardware_transport_fails_without_demo(tmp_path):
    class Absent(FakeWia):
        def open(self,deadline):raise CameraError('disconnected','No camera attached')
    real=SonyPtpDriver(tmp_path,transport=Absent())
    with pytest.raises(CameraError,match='No camera'):real.connect()
    assert not real.connected and not real.get_capabilities().demo


def test_disk_failure_after_camera_transfer_retains_original_for_retry(tmp_path,monkeypatch):
    from app.services.camera import sony_ptp
    real,wire=driver(tmp_path);end=time.monotonic()+3
    reference=real.capture_photo(str(uuid.uuid4()),end);original=wire.photos[0][0]
    write=sony_ptp.atomic_write
    def disk_error(path,data):
        if path.suffix=='.jpg':raise OSError('FAKE disk full')
        write(path,data)
    monkeypatch.setattr(sony_ptp,'atomic_write',disk_error)
    with pytest.raises(OSError):real.get_captured_photo(reference,end)
    assert not wire.photos and real.transfer_cache[reference]==original
    monkeypatch.setattr(sony_ptp,'atomic_write',write)
    assert real.get_captured_photo(reference,end).data==original and wire.shots==1
    assert not real.transfer_cache


def test_receipt_persistence_failure_never_triggers_shutter(tmp_path,monkeypatch):
    from app.services.camera import sony_ptp
    real,wire=driver(tmp_path)
    def fail(*args):raise OSError('FAKE disk full')
    monkeypatch.setattr(sony_ptp,'atomic_write',fail)
    with pytest.raises(OSError):real.capture_photo(str(uuid.uuid4()),time.monotonic()+1)
    assert wire.shots==0


@pytest.mark.skipif(os.name!='nt',reason='Windows COM ABI')
def test_native_escape_abi_against_fake_com_vtable():
    import ctypes as C
    from app.services.camera.sony_wia import _WiaDevice
    assert C.sizeof(_Spec)==(16 if C.sizeof(C.c_void_p)==8 else 8)
    assert C.sizeof(_Variant)==(24 if C.sizeof(C.c_void_p)==8 else 16)
    calls=[]
    callback_type=C.WINFUNCTYPE(C.c_long,C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint32,
                               C.c_void_p,C.c_uint32,C.c_void_p)
    @callback_type
    def escape(this,code,incoming,in_size,outgoing,out_size,actual):
        calls.append((code,C.string_at(incoming,in_size),out_size))
        raw=OUT_HEADER.pack(0x2001,1,7,0,0,0,0,0)+b'example'
        C.memmove(outgoing,raw,len(raw))
        C.cast(actual,C.POINTER(C.c_uint32))[0]=len(raw)
        return 0
    vtable=(C.c_void_p*6)();vtable[4]=C.cast(escape,C.c_void_p)
    interface=C.pointer(C.c_void_p(C.addressof(vtable)))
    device=_WiaDevice.__new__(_WiaDevice);device.extras=C.cast(interface,C.c_void_p)
    packet=encode_command(0x9209)
    assert decode_response(device.exchange(packet,7),7)==b'example'
    assert calls==[(0x100,packet,OUT_HEADER.size+7)]


def test_transfer_timeout_is_reported_as_transfer_not_a_new_shutter(tmp_path):
    from app.config import Settings
    settings=Settings(tmp_path/'host',camera_adapter='sony_zve10',camera_guest_enabled=True)
    wire=FakeWia()
    with TestClient(create_app(settings)) as client:
        client.app.state.camera.adapter.driver.transport=wire
        sid=create(client);base=f'/api/sessions/{sid}/camera'
        assert client.post(base+'/connect',headers=headers()).status_code==200
        wire.fault='transfer_timeout';operation=key()
        response=client.post(base+'/captures',headers=headers(operation),json={'slot_index':0})
        assert response.status_code==504
        assert response.json()['error']['stage']=='transfer'
        assert client.post(base+'/connect',headers=headers()).status_code==200
        assert client.post(base+'/captures',headers=headers(operation),json={'slot_index':0}).status_code==200
        assert wire.shots==1


def test_large_native_jpeg_does_not_use_browser_upload_limit(tmp_path):
    from app.config import Settings
    settings=Settings(tmp_path/'host',camera_adapter='sony_zve10',camera_guest_enabled=True)
    # Valid JPEG APP15 segments, exercising bytes > the browser's 10 MiB limit.
    segment=b'\xff\xef'+struct.pack('>H',60002)+bytes(60000)
    tiny=jpeg('green');large=tiny[:2]+segment*180+tiny[2:]
    assert len(large)>settings.max_upload_bytes
    class LargeCamera(FakeWia):
        def command(self,opcode,params=(),**kwargs):
            result=super().command(opcode,params,**kwargs)
            if opcode==0x9207 and kwargs.get('data')==b'\2\0':self.photos[-1]=(large,self.shots)
            return result
    wire=LargeCamera()
    with TestClient(create_app(settings)) as client:
        client.app.state.camera.adapter.driver.transport=wire
        sid=create(client);base=f'/api/sessions/{sid}/camera'
        assert client.post(base+'/connect',headers=headers()).status_code==200
        response=client.post(base+'/captures',headers=headers(key()),json={'slot_index':0})
        assert response.status_code==200,response.text
        raw=client.get(base+'/captures/'+response.json()['capture']['id']+'/original',headers=headers())
        assert raw.content==large and settings.max_upload_bytes==10*1024*1024


def test_duplicate_request_rechecks_receipt_after_acquiring_capture_lock(tmp_path):
    from app.config import Settings
    settings=Settings(tmp_path/'host',camera_adapter='sony_zve10',camera_guest_enabled=True)
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;wire=FakeWia();camera.adapter.driver.transport=wire
        sid=create(client);base=f'/api/sessions/{sid}/camera'
        assert client.post(base+'/connect',headers=headers()).status_code==200
        original=camera.capture_lock;entered=threading.Event();resume=threading.Event()
        class SchedulingGap:
            calls=0
            def acquire(self,blocking=False):
                self.calls+=1
                if self.calls==1:entered.set();assert resume.wait(5)
                return original.acquire(blocking=blocking)
            def release(self):original.release()
            def locked(self):return original.locked()
        camera.capture_lock=SchedulingGap();operation=key()
        def request():return client.post(base+'/captures',headers=headers(operation),json={'slot_index':0})
        with ThreadPoolExecutor() as pool:
            delayed=pool.submit(request)
            try:
                assert entered.wait(3)
                first=request();assert first.status_code==200,first.text
            finally:resume.set()
            replay=delayed.result(timeout=5)
        assert replay.status_code==200 and replay.json()==first.json() and wire.shots==1


def test_usb_disconnect_closes_old_transport_and_explicit_reconnect_recovers(tmp_path):
    real,wire=driver(tmp_path);real.start_live_view()
    original=wire.command
    def unplug(operation,*args,**kwargs):
        if operation==0x1009:raise CameraError('disconnected','FAKE USB removal')
        return original(operation,*args,**kwargs)
    wire.command=unplug
    with pytest.raises(CameraError,match='USB removal'):real.get_preview_frame()
    assert not real.connected and not wire.connected and wire.closed==1
    wire.command=original
    real.connect();real.start_live_view()
    assert real.get_preview_frame().data==wire.preview and wire.open_count==2 and wire.shots==0


@pytest.mark.parametrize('failure',['busy','camera_mode'])
def test_preflight_failure_can_retry_same_key_without_an_existing_shutter(tmp_path,failure):
    from app.config import Settings
    settings=Settings(tmp_path/'host',camera_adapter='sony_zve10',camera_guest_enabled=True)
    wire=FakeWia()
    with TestClient(create_app(settings)) as client:
        client.app.state.camera.adapter.driver.transport=wire
        sid=create(client);base=f'/api/sessions/{sid}/camera'
        assert client.post(base+'/connect',headers=headers()).status_code==200
        command=wire.command;blocked=True
        def preflight(operation,*args,**kwargs):
            nonlocal blocked
            if operation==0x9209 and blocked and failure=='busy':
                blocked=False
                return decode_response(OUT_HEADER.pack(0x2019,0,0,0,0,0,0,0),0)
            return command(operation,*args,**kwargs)
        wire.command=preflight
        if failure=='camera_mode':wire.drive=2
        operation=key();response=client.post(base+'/captures',headers=headers(operation),json={'slot_index':0})
        assert response.json()['error']['code']==failure and wire.shots==0
        identifier=response.json()['error']['capture_id']
        assert not client.app.state.camera.adapter.driver._paths(identifier)[0].exists()
        wire.drive=1
        retry=client.post(base+'/captures',headers=headers(operation),json={'slot_index':0})
        assert retry.status_code==200,retry.text
        assert retry.json()['capture']['id']==identifier and wire.shots==1
