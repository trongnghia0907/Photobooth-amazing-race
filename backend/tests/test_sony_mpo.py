"""JPEG/MPF originals: synthetic MPOs only, never camera hardware or user files."""
from io import BytesIO
import hashlib
import json
import time
import uuid

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from fastapi import HTTPException
from app.config import Settings
from app.main import create_app
from app.services.images import validate_image
from app.services.camera.base import CameraError, CapturedPhoto
from app.services.camera.sony_ptp import check_jpeg, SonyPtpDriver
from app.services.camera.sony_zve10 import SonyZvE10CameraAdapter
from test_sony_ptp import FakeWia
from test_sony_zve10 import settings, connect, capture
from test_sessions import create, headers, key


def mpo():
    out=BytesIO()
    Image.new('RGB',(320,240),'blue').save(out,format='MPO',save_all=True,
        append_images=[Image.new('RGB',(80,60),'red')])
    data=out.getvalue()
    with Image.open(BytesIO(data)) as image:assert image.format=='MPO' and image.n_frames==2
    return data


def test_mpo_primary_jpeg_passes_validation_and_normalization(tmp_path):
    data=mpo();assert check_jpeg(data)==(320,240)
    result=validate_image(data,'image/jpeg',Settings(tmp_path))
    assert result.input_hash==hashlib.sha256(data).hexdigest()
    with Image.open(BytesIO(result.data)) as normalized:
        assert normalized.size==(320,240) and normalized.format=='PNG'
        assert normalized.getpixel((10,10))[2]>200  # Primary blue, never red thumbnail.
    with pytest.raises(HTTPException):validate_image(data,'image/png',Settings(tmp_path))
    with pytest.raises(CameraError):check_jpeg(data[:len(data)//4])


class MpoCamera(FakeWia):
    def __init__(self):super().__init__();self.original=mpo()
    def command(self,opcode,params=(),**kwargs):
        result=super().command(opcode,params,**kwargs)
        if opcode==0x9207 and kwargs.get('data')==b'\x02\x00':self.photos[-1]=(self.original,self.shots)
        return result


@pytest.mark.parametrize('count',[4,6])
def test_host_mpo_originals_retake_replay_and_primary_editor_image(settings,count):
    with TestClient(create_app(settings)) as client:
        wire=MpoCamera();client.app.state.camera.adapter.driver.transport=wire
        sid=create(client,layout='landscape_4' if count==4 else 'grid2x3',slot_count=count);base=connect(client,sid)
        for slot in range(count):
            operation=key();response=capture(client,base,slot,operation)
            assert response.status_code==200,response.text
            state=response.json();cid=state['capture']['id']
            raw=client.get(base+'/captures/'+cid+'/original',headers=headers())
            assert raw.content==wire.original
            photo=next(p for p in state['session']['photos'] if p['slot_index']==slot)
            png=client.get(f'/api/sessions/{sid}/photos/{photo["id"]}/image',headers=headers())
            with Image.open(BytesIO(png.content)) as image:assert image.size==(320,240) and image.getpixel((10,10))[2]>200
            assert capture(client,base,slot,operation).json()==state
        assert capture(client,base,1).status_code==200
        assert wire.shots==count+1


def seed_rejected(driver,wire,reference,data):
    journal,_=driver._paths(reference);record=json.loads(journal.read_text())
    digest=hashlib.sha256(data).hexdigest();path=driver.root/'rejected'/(reference+'-'+digest+'.bin')
    path.parent.mkdir(exist_ok=True);path.write_bytes(data)
    record['object']={'format':0x3801,'width':0,'height':0,'size':len(data),'sequence':0,'name':'DSC00001.JPG'}
    record['rejected_transfer']={'bytes':len(data),'sha256':digest,'path':path.relative_to(driver.root.parent.parent).as_posix(),'error':'Old JPEG-only check'}
    journal.write_text(json.dumps(record));wire.photos.clear()
    return path


def test_retry_recovers_old_rejected_mpo_without_usb_transfer_or_shutter(tmp_path):
    wire=MpoCamera();driver=SonyPtpDriver(tmp_path,transport=wire);driver.connect();end=time.monotonic()+5
    reference=driver.capture_photo(str(uuid.uuid4()),end)
    retained=seed_rejected(driver,wire,reference,wire.original);commands=len(wire.commands)
    assert driver.get_captured_photo(reference,end).data==wire.original
    assert len(wire.commands)==commands and wire.shots==1
    assert retained.read_bytes()==wire.original


def test_handoff_preserves_old_rejected_mpo_before_new_shutter(tmp_path):
    wire=MpoCamera();driver=SonyPtpDriver(tmp_path,transport=wire);driver.connect();end=time.monotonic()+5
    reference=driver.capture_photo(str(uuid.uuid4()),end)
    seed_rejected(driver,wire,reference,wire.original);old=str(uuid.uuid4());new=str(uuid.uuid4())
    result=driver.supersede_capture(reference,old,new,end)
    assert (tmp_path/result['path']).read_bytes()==wire.original
    driver.capture_photo(str(uuid.uuid4()),end);assert wire.shots==2
