"""Normal shutter mapping and old-intent release; FakeWia only."""
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.camera.base import CameraError
from app.services.camera.sony_ptp import SonyPtpDriver,SHUTTER_RELEASE,HALF_RELEASE
from test_sony_ptp import FakeWia,ONE_SHOT,driver
from test_sony_zve10 import settings,connect,capture
from test_sessions import create,key

class AckOnlySecondOneShot(FakeWia):
    """Observed failure: the second one-shot request ACKs without a JPEG.

    This models the symptom, not an assertion about the camera's internal cause.
    Normal shutter press/release is a separate, advertised control.
    """
    one_shots=0
    def command(self,opcode,params=(),**kwargs):
        if opcode==0x9207 and params==(ONE_SHOT,) and kwargs.get('data')==b'\2\0':
            self.one_shots+=1
            if self.one_shots>1:
                self.commands.append((opcode,params,kwargs['data']))
                return b''  # Valid ACK, but no image was produced.
        return super().command(opcode,params,**kwargs)


@pytest.mark.parametrize('count',[4,6])
def test_normal_shutter_sequence_does_not_depend_on_one_shot_request(settings,monkeypatch,count):
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;wire=AckOnlySecondOneShot();camera.adapter.driver.transport=wire
        def no_image(_deadline):raise CameraError('timeout','TEST no JPEG after acknowledged request',stage='transfer')
        monkeypatch.setattr(camera.adapter.driver,'_wait',no_image)
        sid=create(client,layout='landscape_4' if count==4 else 'grid2x3',slot_count=count)
        base=connect(client,sid)
        for slot in range(count):
            operation=key();result=capture(client,base,slot,operation)
            assert result.status_code==200,result.text
            assert result.json()['capture']['slot_index']==slot
            assert capture(client,base,slot,operation).json()==result.json()
        controls=[(params,data) for op,params,data in wire.commands if op==0x9207]
        assert controls==[item for _ in range(count) for item in (
            ((HALF_RELEASE,),b'\2\0'),((SHUTTER_RELEASE,),b'\2\0'),
            ((SHUTTER_RELEASE,),b'\1\0'),((HALF_RELEASE,),b'\1\0'))]
        assert wire.shots==count and wire.one_shots==0


@pytest.mark.parametrize('stored_control',[None,ONE_SHOT,SHUTTER_RELEASE])
def test_pending_release_uses_the_original_journaled_control(tmp_path,stored_control):
    camera,wire=driver(tmp_path);identifier=str(uuid.uuid4());journal,_=camera._paths(identifier)
    record={'status':'dispatched','object':None,'release_pending':True}
    if stored_control is not None:record['shutter_control']=stored_control
    journal.write_text(json.dumps(record));before=len(wire.commands)
    camera.recover_capture(identifier,time.monotonic()+2)
    expected=ONE_SHOT if stored_control is None else stored_control
    assert wire.commands[before:]==[(0x9207,(expected,),b'\1\0')]
    camera.recover_capture(identifier,time.monotonic()+2)
    assert wire.shots==0 and len(wire.commands)==before+1


@pytest.mark.parametrize('control',[0xd2c1,None,'53954',True])
def test_unknown_receipt_control_never_sends_a_camera_command(tmp_path,control):
    camera,wire=driver(tmp_path);identifier=str(uuid.uuid4());journal,_=camera._paths(identifier)
    record={'status':'dispatched','object':None,'release_pending':True,'shutter_control':control}
    journal.write_text(json.dumps(record));before=len(wire.commands)
    with pytest.raises(CameraError,match='Unknown shutter control'):
        camera.recover_capture(identifier,time.monotonic()+2)
    assert len(wire.commands)==before and wire.shots==0
    assert json.loads(journal.read_text())==record


def test_only_one_shot_advertised_is_not_normal_shutter_support(tmp_path):
    wire=FakeWia();wire.controls=[ONE_SHOT]
    camera=SonyPtpDriver(tmp_path,transport=wire)
    with pytest.raises(CameraError,match='required ZV-E10 PTP 2'):
        camera.connect()
    assert wire.shots==0 and not any(op==0x9207 for op,_,_ in wire.commands)


def test_normal_shutter_does_not_require_one_shot_support(tmp_path):
    wire=FakeWia();wire.controls=[SHUTTER_RELEASE,HALF_RELEASE]
    camera=SonyPtpDriver(tmp_path,transport=wire);camera.connect()
    try:
        identifier=str(uuid.uuid4());deadline=time.monotonic()+2
        camera.capture_photo(identifier,deadline)
        assert camera.get_captured_photo(identifier,deadline).data
        assert wire.shots==1
    finally:camera.disconnect()
