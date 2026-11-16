"""Session handoff against FakeWia only: NEVER opens hardware or operator data."""
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.camera.base import CameraError
from test_sony_ptp import FakeWia, jpeg
from test_sony_zve10 import settings, connect, capture
from test_sessions import create, headers, key


def pending(client,wire):
    sid=create(client);base=connect(client,sid);operation=key()
    wire.fault='transfer_timeout'
    result=capture(client,base,0,operation)
    assert result.status_code!=200
    with client.app.state.repository.db.connect() as db:
        row=db.execute('SELECT * FROM camera_captures WHERE session_id=?',(sid,)).fetchone()
    return sid,base,operation,row['id']


def new_session(client,old_sid,count=6):
    assert client.post(f'/api/sessions/{old_sid}/camera/disconnect',headers=headers()).status_code==200
    sid=create(client,layout='landscape_4' if count==4 else 'grid2x3',slot_count=count)
    return sid,connect(client,sid)


@pytest.mark.parametrize('count',[4,6])
def test_failed_old_transfer_is_quarantined_then_new_session_captures(settings,count):
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;wire=FakeWia();camera.adapter.driver.transport=wire
        a,base_a,old_key,cid=pending(client,wire);original=wire.photos[0][0]
        b,base_b=new_session(client,a,count)
        operation=key();result=capture(client,base_b,0,operation)
        assert result.status_code==200,result.text
        state=result.json();assert state['capture']['session_id']==b
        saved=settings.storage_root/'camera_originals'/a/(cid+'.jpg')
        assert saved.read_bytes()==original
        with camera.repo.db.connect() as db:
            old=db.execute('SELECT * FROM camera_captures WHERE id=?',(cid,)).fetchone()
            assert old['error_code']=='capture_superseded' and old['native_sha256']==hashlib.sha256(original).hexdigest()
            assert db.execute('SELECT COUNT(*) FROM slots WHERE session_id=?',(a,)).fetchone()[0]==0
        assert capture(client,base_a,0,old_key).json()['error']['code']=='capture_superseded'
        assert capture(client,base_b,0,operation).json()==state
        for slot in range(1,count):assert capture(client,base_b,slot).status_code==200
        assert wire.shots==count+1


def test_empty_retired_capture_and_late_old_jpeg_never_enter_new_slots(settings):
    with TestClient(create_app(settings)) as client:
        wire=FakeWia();camera=client.app.state.camera;camera.adapter.driver.transport=wire
        a,_,_,cid=pending(client,wire);wire.photos.clear()
        journal,_=camera.adapter.driver._paths(cid)
        record=json.loads(journal.read_text());record['object']=None;journal.write_text(json.dumps(record))
        b,base=new_session(client,a)
        assert capture(client,base,0).status_code==200
        late=jpeg('purple');wire.photos.append((late,1))
        assert capture(client,base,1).status_code==200
        assert (settings.storage_root/'camera_originals'/a/(cid+'.jpg')).read_bytes()==late
        with camera.repo.db.connect() as db:
            rows=db.execute('SELECT native_sha256 FROM camera_captures WHERE session_id=?',(b,)).fetchall()
        assert all(row[0]!=hashlib.sha256(late).hexdigest() for row in rows)
        assert wire.shots==3


def test_current_session_retry_keeps_same_shutter_and_original(settings):
    with TestClient(create_app(settings)) as client:
        wire=FakeWia();client.app.state.camera.adapter.driver.transport=wire
        _,base,operation,_=pending(client,wire)
        assert client.post(base+'/connect',headers=headers()).status_code==200
        assert capture(client,base,0,operation).status_code==200
        assert wire.shots==1


def test_consumed_old_buffer_with_object_metadata_does_not_wait_forever(settings,monkeypatch):
    from app.services.camera import sony_ptp
    parse=sony_ptp.object_info
    monkeypatch.setattr(sony_ptp,'object_info',lambda data:{**parse(data),'width':0,'height':0})
    with TestClient(create_app(settings)) as client:
        wire=FakeWia();camera=client.app.state.camera;driver=camera.adapter.driver;driver.transport=wire
        a,_,_,cid=pending(client,wire)
        journal,_=driver._paths(cid);record=json.loads(journal.read_text())
        # Reproduce the actual ZV-E10 receipt: ObjectInfo obtained, GetObject
        # consumed the image, no successfully persisted JPEG, unknown dimensions.
        assert record['object']['width']==record['object']['height']==0
        wire.photos.clear()
        b,base=new_session(client,a)
        result=capture(client,base,0)
        assert result.status_code==200,result.text
        record=json.loads(journal.read_text())
        assert record['status']=='superseded'
        assert record['capture_outcome']=='buffer_empty_original_unavailable'
        assert record['object']['name'] and record['last_buffer_value']==0
        assert not (settings.storage_root/'camera_originals'/a/(cid+'.jpg')).exists()
        assert wire.shots==2


def test_empty_old_tombstone_cannot_consume_current_sessions_retry(settings):
    with TestClient(create_app(settings)) as client:
        wire=FakeWia();camera=client.app.state.camera;driver=camera.adapter.driver;driver.transport=wire
        a,_,_,cid=pending(client,wire);wire.photos.clear()
        journal,_=driver._paths(cid);record=json.loads(journal.read_text());record['object']=None;journal.write_text(json.dumps(record))
        b,base=new_session(client,a);operation=key();wire.fault='transfer_timeout'
        assert capture(client,base,0,operation).status_code!=200
        expected=wire.photos[0][0]
        assert client.post(base+'/connect',headers=headers()).status_code==200
        result=capture(client,base,0,operation)
        assert result.status_code==200,result.text
        assert result.json()['capture']['native_sha256']==hashlib.sha256(expected).hexdigest()
        assert not (settings.storage_root/'camera_originals'/a/(cid+'.jpg')).exists()
        assert wire.shots==2


def test_older_tab_cannot_supersede_newer_sessions_pending_capture(settings):
    with TestClient(create_app(settings)) as client:
        wire=FakeWia();camera=client.app.state.camera;driver=camera.adapter.driver;driver.transport=wire
        a=create(client);connect(client,a)
        b,base=new_session(client,a);wire.fault='transfer_timeout'
        assert capture(client,base,0).status_code!=200
        with camera.repo.db.connect() as db:
            cid=db.execute('SELECT id FROM camera_captures WHERE session_id=?',(b,)).fetchone()[0]
        journal,_=driver._paths(cid);before=journal.read_bytes()
        assert client.post(base+'/disconnect',headers=headers()).status_code==200
        old_base=connect(client,a)
        assert capture(client,old_base,0).status_code!=200
        assert journal.read_bytes()==before and wire.shots==1


@pytest.mark.parametrize('failure',['busy','release_busy','pending_buffer','disconnected'])
def test_physical_uncertainty_blocks_new_shutter_and_can_recover(settings,monkeypatch,failure):
    with TestClient(create_app(settings)) as client:
        wire=FakeWia();camera=client.app.state.camera;driver=camera.adapter.driver;driver.transport=wire
        a,_,_,cid=pending(client,wire);b,base=new_session(client,a)
        journal,_=driver._paths(cid);record=json.loads(journal.read_text())
        original=driver._properties
        if failure=='release_busy':
            record['release_pending']=True;journal.write_text(json.dumps(record))
            command=driver._command
            def blocked_release(opcode,*args,**kwargs):
                if opcode==0x9207:raise CameraError('busy','TEST release still busy')
                return command(opcode,*args,**kwargs)
            monkeypatch.setattr(driver,'_command',blocked_release)
        else:
            def unavailable(deadline):
                if failure=='pending_buffer':
                    props=original(deadline);props[0xd215]['value']=1;return props
                raise CameraError('busy' if failure=='busy' else 'disconnected','TEST physical unavailable')
            monkeypatch.setattr(driver,'_properties',unavailable)
        result=capture(client,base,0);assert result.status_code!=200 and wire.shots==1
        assert not list((settings.storage_root/'camera_originals'/b).glob('*.jpg'))
        assert journal.exists() and wire.photos


def test_unknown_shutter_finishes_only_release_before_quarantining(settings):
    with TestClient(create_app(settings)) as client:
        wire=FakeWia();camera=client.app.state.camera;driver=camera.adapter.driver;driver.transport=wire
        a,_,_,cid=pending(client,wire);b,base=new_session(client,a)
        journal,_=driver._paths(cid);record=json.loads(journal.read_text())
        record['release_pending']=True;journal.write_text(json.dumps(record));before=len(wire.commands)
        assert capture(client,base,0).status_code==200
        controls=[data for op,_params,data in wire.commands[before:] if op==0x9207]
        assert controls==[b'\x01\x00',b'\x02\x00',b'\x01\x00']
        assert wire.shots==2


def test_restart_reconciles_superseded_receipt_without_resurrecting_old_request(settings):
    wire=FakeWia()
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        a,base_a,operation,cid=pending(client,wire);b,base_b=new_session(client,a)
        # Crash boundary: receipt/file committed but SQLite handoff not yet written.
        camera.adapter.driver.supersede_capture(cid,a,b,__import__('time').monotonic()+5)
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        connect(client,b)
        assert capture(client,base_b,0).status_code==200
        assert capture(client,base_a,0,operation).json()['error']['code']=='capture_superseded'
        assert wire.shots==2


def test_active_transfer_cannot_be_superseded_by_another_session(settings,monkeypatch):
    with TestClient(create_app(settings)) as client:
        wire=FakeWia();camera=client.app.state.camera;camera.adapter.driver.transport=wire
        a=create(client);base=connect(client,a);entered=threading.Event();release=threading.Event()
        original=camera.adapter.driver.get_captured_photo
        def slow(*args,**kwargs):
            entered.set();assert release.wait(5);return original(*args,**kwargs)
        monkeypatch.setattr(camera.adapter.driver,'get_captured_photo',slow)
        with ThreadPoolExecutor() as pool:
            shot=pool.submit(capture,client,base,0)
            try:
                assert entered.wait(2)
                assert client.post(base+'/disconnect',headers=headers()).status_code==409
                b=create(client)
                assert client.post(f'/api/sessions/{b}/camera/connect',headers=headers()).status_code==409
            finally:release.set()
            assert shot.result().status_code==200
        assert wire.shots==1
        assert camera.owner is None  # Explicit release waits for transfer completion.
        connect(client,b)
        assert capture(client,f'/api/sessions/{b}/camera',0).status_code==200
        assert wire.shots==2
