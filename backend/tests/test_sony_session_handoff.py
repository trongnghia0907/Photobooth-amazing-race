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
from test_sony_mpo import mpo
from test_sony_cancel import load_cli
from app.services.camera.sony_ptp import SonyPtpDriver
from test_sony_zve10 import settings, connect, capture
from test_sessions import create, headers, key


def received_checkpoint(client,capture_id,data):
    # Model a crash after the validated-byte hash checkpoint, before its cache
    # file was persisted. Metadata-only timeouts deliberately get NO checkpoint.
    journal,_=client.app.state.camera.adapter.driver._paths(capture_id)
    record=json.loads(journal.read_text());record['received_sha256']=hashlib.sha256(data).hexdigest()
    journal.write_text(json.dumps(record))


def pending(client,wire,*,known_original=False):
    sid=create(client);base=connect(client,sid);operation=key()
    wire.fault='transfer_timeout'
    result=capture(client,base,0,operation)
    assert result.status_code!=200
    with client.app.state.repository.db.connect() as db:
        row=db.execute('SELECT * FROM camera_captures WHERE session_id=?',(sid,)).fetchone()
    if known_original:received_checkpoint(client,row['id'],wire.photos[0][0])
    return sid,base,operation,row['id']


def new_session(client,old_sid,count=6):
    assert client.post(f'/api/sessions/{old_sid}/camera/disconnect',headers=headers()).status_code==200
    sid=create(client,layout='landscape_4' if count==4 else 'grid2x3',slot_count=count)
    return sid,connect(client,sid)


@pytest.mark.parametrize('count',[4,6])
def test_failed_old_transfer_is_quarantined_then_new_session_captures(settings,count):
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;wire=FakeWia();camera.adapter.driver.transport=wire
        a,base_a,old_key,cid=pending(client,wire,known_original=True);original=wire.photos[0][0]
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
        # Keep the receipt's evidence that GetObject had already started.
        b,base=new_session(client,a)
        assert capture(client,base,0).status_code==200
        late=jpeg('purple');wire.photos.append((late,1))
        result=capture(client,base,1)
        assert result.json()['error']['code']=='recovery_required'
        assert wire.photos[0][0]==late  # Unknown late image is NOT labelled as A.
        assert not (settings.storage_root/'camera_originals'/a/(cid+'.jpg')).exists()
        with camera.repo.db.connect() as db:
            rows=db.execute('SELECT native_sha256 FROM camera_captures WHERE session_id=?',(b,)).fetchall()
        assert all(row[0]!=hashlib.sha256(late).hexdigest() for row in rows)
        assert wire.shots==2


@pytest.mark.parametrize('payload',['filename_only','mpo','corrupt','interrupted'])
def test_operator_preserves_buffer_without_relabeling_or_retrying(settings,monkeypatch,payload):
    wire=FakeWia()
    with TestClient(create_app(settings)) as client:
        driver=client.app.state.camera.adapter.driver;driver.transport=wire
        a,_,_,cid=pending(client,wire)
        previous=wire.photos.pop()[0]
        b,base=new_session(client,a)
        assert capture(client,base,0).status_code==200
        journal,_=driver._paths(cid)
        record=json.loads(journal.read_bytes())
        record.pop('transfer_attempted')  # Legacy audited empty receipt remains retired after later observations.
        journal.write_text(json.dumps(record))
        data=previous if payload=='filename_only' else mpo()
        wire.photos.append((data,999))
        blocked=capture(client,base,1).json()['error']
        assert blocked['code']=='recovery_required' and blocked['shutter_dispatched'] is False
        assert wire.photos[0][0]==data and wire.shots==2
    original_receipt=journal.read_bytes()
    cli=load_cli()
    monkeypatch.setattr(cli,'SonyPtpDriver',lambda storage,timeout:SonyPtpDriver(storage,timeout,transport=wire))
    monkeypatch.setattr(cli,'probe_windows',lambda timeout:{'status':'QUERIED','devices':[{'original_zv_e10_name_match':True,'pnp_status':'OK'}]})
    def recover():
        return cli.cancel(settings.storage_root,cid,confirm_discard=False,preserve_buffer=True)
    offset=len(wire.commands)
    if payload in ('corrupt','interrupted'):
        wire.fault='bad_jpeg' if payload=='corrupt' else 'transfer_timeout'
        with pytest.raises(CameraError):recover()
        commands=len(wire.commands)
        with pytest.raises(CameraError):recover()
        assert all(op!=0x1009 for op,_,_ in wire.commands[commands:])
        assert bool(list((journal.parent/'unassigned').glob('*.bin')))==(payload=='corrupt')
        # An empty buffer after an incomplete operator transfer is insufficient.
        wire.photos.clear()
        with TestClient(create_app(settings)) as client:
            client.app.state.camera.adapter.driver.transport=wire
            base=connect(client,create(client))
            assert capture(client,base,0).json()['error']['code']=='camera_recovery_pending'
        assert wire.shots==2
    else:
        preserved=recover()
        assert preserved['file_info_before']==0x8001 and preserved['file_info_after']==0
        assert preserved['attribution']=='unassigned' and preserved['matched_capture_ids']==[]
        original=settings.storage_root/preserved['original_path']
        assert original.read_bytes()==data and preserved['sha256']==hashlib.sha256(data).hexdigest()
        assert recover()==preserved and journal.read_bytes()==original_receipt
        assert sum(op==0x1009 for op,_,_ in wire.commands[offset:])==1
        assert all(op!=0x9207 for op,_,_ in wire.commands[offset:])
        with TestClient(create_app(settings)) as client:
            camera=client.app.state.camera;camera.adapter.driver.transport=wire
            sid=create(client);base=connect(client,sid)
            for slot in range(2):assert capture(client,base,slot).status_code==200
            with camera.repo.db.connect() as db:
                hashes=[row[0] for row in db.execute('SELECT native_sha256 FROM camera_captures WHERE session_id=?',(sid,))]
            assert preserved['sha256'] not in hashes or payload=='filename_only'  # FakeWia repeats its color fixtures.
        assert wire.shots==4 and original.read_bytes()==data


def test_current_session_retry_keeps_same_shutter_and_original(settings):
    with TestClient(create_app(settings)) as client:
        wire=FakeWia();client.app.state.camera.adapter.driver.transport=wire
        _,base,operation,_=pending(client,wire,known_original=True)
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
        # The failed transfer consumed the buffer; its ObjectInfo remains.
        b,base=new_session(client,a);operation=key();wire.fault='transfer_timeout'
        assert capture(client,base,0,operation).status_code!=200
        expected=wire.photos[0][0]
        with camera.repo.db.connect() as db:
            current_id=db.execute('SELECT id FROM camera_captures WHERE session_id=? AND request_key=?',(b,operation)).fetchone()[0]
        received_checkpoint(client,current_id,expected)
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
        a,_,_,cid=pending(client,wire,known_original=True);b,base=new_session(client,a)
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
        operation=key();result=capture(client,base,0,operation);assert result.status_code!=200 and wire.shots==1
        assert not list((settings.storage_root/'camera_originals'/b).glob('*.jpg'))
        assert journal.exists() and wire.photos
        # Once the simulated physical barrier clears, the identical B request
        # may reconcile A and send exactly ONE new shutter, never replay A's.
        if failure=='release_busy':monkeypatch.setattr(driver,'_command',command)
        else:monkeypatch.setattr(driver,'_properties',original)
        result=capture(client,base,0,operation)
        assert result.status_code==200,result.text
        assert wire.shots==2
        assert capture(client,base,0,operation).json()==result.json() and wire.shots==2


def test_unknown_shutter_finishes_only_release_before_quarantining(settings):
    with TestClient(create_app(settings)) as client:
        wire=FakeWia();camera=client.app.state.camera;driver=camera.adapter.driver;driver.transport=wire
        a,_,_,cid=pending(client,wire,known_original=True);b,base=new_session(client,a)
        journal,_=driver._paths(cid);record=json.loads(journal.read_text())
        record['release_pending']=True;journal.write_text(json.dumps(record));before=len(wire.commands)
        assert capture(client,base,0).status_code==200
        controls=[data for op,_params,data in wire.commands[before:] if op==0x9207]
        assert controls==[b'\x01\x00',b'\x02\x00',b'\x02\x00',b'\x01\x00',b'\x01\x00']
        assert wire.shots==2


def test_restart_reconciles_superseded_receipt_without_resurrecting_old_request(settings):
    wire=FakeWia()
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        a,base_a,operation,cid=pending(client,wire,known_original=True);b,base_b=new_session(client,a)
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


@pytest.mark.parametrize('restart',[False,True])
def test_retired_session_cannot_reopen_capture_with_a_new_request_key(settings,restart):
    wire=FakeWia()
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        a,base_a,_,cid=pending(client,wire,known_original=True)
        b,base_b=new_session(client,a)
        first=capture(client,base_b,0);assert first.status_code==200,first.text
        assert client.post(base_b+'/disconnect',headers=headers()).status_code==200
        if not restart:
            connect(client,a)
            result=capture(client,base_a,1)
            assert result.json()['error']['code']=='capture_superseded',result.text
            assert wire.shots==2
    if restart:
        with TestClient(create_app(settings)) as client:
            camera=client.app.state.camera;camera.adapter.driver.transport=wire
            connect(client,a)
            result=capture(client,base_a,1)
            assert result.json()['error']['code']=='capture_superseded',result.text
            assert wire.shots==2


@pytest.mark.parametrize('restart',[False,True])
def test_empty_buffer_does_not_prove_uncertain_shutter_finished(settings,restart):
    wire=FakeWia()
    def blocked(client):
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        base=connect(client,b);operation=key()
        result=capture(client,base,0,operation)
        assert result.json()['error']['code']=='camera_recovery_pending',result.text
        assert result.json()['error']['shutter_dispatched'] is False
        progress=client.get(base+'/status',headers=headers(operation)).json()['capture_progress']
        assert progress['stage']=='blocked_before_shutter' and not progress['shutter_acknowledged']
        assert wire.shots==1
        journal,_=camera.adapter.driver._paths(cid)
        assert json.loads(journal.read_text())['status']!='superseded'
        # A's delayed synthetic exposure arrives only AFTER B tried to start.
        wire.photos.append(late)
        result=capture(client,base,0,operation)
        assert result.json()['error']['code']=='recovery_required',result.text
        assert wire.photos[0]==late and wire.shots==1
        with camera.repo.db.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM slots WHERE session_id=?',(b,)).fetchone()[0]==0
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        a=create(client);base_a=connect(client,a);wire.fault='shutter_timeout'
        assert capture(client,base_a,0).status_code!=200
        late=wire.photos.pop()
        with camera.repo.db.connect() as db:
            cid=db.execute('SELECT id FROM camera_captures WHERE session_id=?',(a,)).fetchone()[0]
        assert client.post(base_a+'/disconnect',headers=headers()).status_code==200
        b=create(client)
        if not restart:blocked(client)
    if restart:
        with TestClient(create_app(settings)) as client:blocked(client)


@pytest.mark.parametrize('restart',[False,True])
def test_late_checksum_bound_original_stays_under_A_identity(settings,restart):
    wire=FakeWia()
    def finish(client):
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        if restart:connect(client,b)
        wire.photos.append(late)
        operation=key();result=capture(client,base_b,1,operation)
        assert result.status_code==200,result.text
        original=settings.storage_root/'camera_originals'/a/(cid+'.jpg')
        assert original.read_bytes()==late[0]
        journal,_=camera.adapter.driver._paths(cid)
        receipt=json.loads(journal.read_text())
        assert receipt['status']=='superseded' and receipt['session_id']==a
        assert receipt['sha256']==hashlib.sha256(late[0]).hexdigest()
        with camera.repo.db.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM slots WHERE session_id=?',(a,)).fetchone()[0]==0
            row=db.execute('SELECT * FROM camera_captures WHERE id=?',(cid,)).fetchone()
            assert row['native_path']==original.relative_to(settings.storage_root).as_posix()
            assert row['error_code']=='capture_superseded'
        assert result.json()['capture']['id']!=cid and result.json()['capture']['session_id']==b
        assert wire.shots==3
        assert capture(client,base_b,1,operation).json()==result.json() and wire.shots==3
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        a,_,_,cid=pending(client,wire,known_original=True);late=wire.photos.pop()
        b,base_b=new_session(client,a)
        assert capture(client,base_b,0).status_code==200
        if not restart:finish(client)
    if restart:
        with TestClient(create_app(settings)) as client:finish(client)


def test_receipt_alone_blocks_stale_A_after_crash_before_sqlite_handoff(settings):
    wire=FakeWia()
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        a,base_a,_,cid=pending(client,wire,known_original=True)
        b,_=new_session(client,a)
        camera.adapter.driver.supersede_capture(cid,a,b,__import__('time').monotonic()+5)
        with camera.repo.db.connect() as db:
            assert db.execute('SELECT error_code FROM camera_captures WHERE id=?',(cid,)).fetchone()[0]!='capture_superseded'
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        connect(client,a)
        result=capture(client,base_a,1)
        assert result.json()['error']['code']=='capture_superseded',result.text
        assert wire.shots==1
        assert (settings.storage_root/'camera_originals'/a/(cid+'.jpg')).exists()


def test_checkpoint_write_failure_recovers_A_before_B_shutter(settings,monkeypatch):
    from app.services.camera import sony_ptp
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;wire=FakeWia();driver=camera.adapter.driver;driver.transport=wire
        a=create(client);base_a=connect(client,a);original=jpeg('red');write=sony_ptp.atomic_write
        def fail_checkpoint(path,payload):
            if path.suffix=='.json' and b'received_sha256' in payload:raise OSError('TEST checkpoint fsync failed')
            return write(path,payload)
        monkeypatch.setattr(sony_ptp,'atomic_write',fail_checkpoint)
        result=capture(client,base_a,0);assert result.status_code==503
        with camera.repo.db.connect() as db:
            cid=db.execute('SELECT id FROM camera_captures WHERE session_id=?',(a,)).fetchone()[0]
        assert driver.transfer_cache[cid]==original and wire.shots==1
        monkeypatch.setattr(sony_ptp,'atomic_write',write)
        b,base_b=new_session(client,a)
        result=capture(client,base_b,0);assert result.status_code==200,result.text
        assert (settings.storage_root/'camera_originals'/a/(cid+'.jpg')).read_bytes()==original
        assert result.json()['capture']['native_sha256']!=hashlib.sha256(original).hexdigest()
        assert result.json()['capture']['session_id']==b and wire.shots==2
        assert cid not in driver.transfer_cache and cid not in driver.transfer_hashes


@pytest.mark.parametrize('restart',[False,True])
@pytest.mark.parametrize('physical',['empty','busy','pending','late_jpeg'])
def test_legacy_closed_empty_receipt_does_not_reopen_a_resolved_handoff(settings,monkeypatch,restart,physical):
    wire=FakeWia()
    def verify(client):
        driver=client.app.state.camera.adapter.driver
        if physical in ('busy','pending'):
            original=driver._properties
            def unavailable(deadline):
                if physical=='busy':raise CameraError('busy','TEST WIA still busy')
                values=original(deadline);values[0xd215]['value']=1;return values
            monkeypatch.setattr(driver,'_properties',unavailable)
        elif physical=='late_jpeg':wire.photos.append((jpeg('purple'),777))
        before=len(wire.commands);result=capture(client,base,0)
        if physical=='empty':
            assert result.status_code==200,result.text
            assert wire.shots==2 and journal.read_bytes()==closed
        else:
            expected={'busy':'busy','pending':'camera_recovery_pending','late_jpeg':'recovery_required'}[physical]
            assert result.json()['error']['code']==expected,result.text
            assert wire.shots==1
            assert not any(op in (0x1009,0x9207) for op,_params,_data in wire.commands[before:])
            if physical=='late_jpeg':assert wire.photos[0][1]==777
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;driver=camera.adapter.driver;driver.transport=wire
        a,_,_,cid=pending(client,wire);wire.photos.clear()
        b,base=new_session(client,a)
        journal,_=driver._paths(cid);record=json.loads(journal.read_text())
        # Exact legacy state: already retired after an empty-buffer check,
        # with original ObjectInfo, but predating transfer_attempted receipts.
        record.pop('transfer_attempted',None)
        record.update(status='superseded',session_id=a,superseded_by=b,
            capture_outcome='buffer_empty_original_unavailable',last_buffer_value=0,
            buffer_checked_at='2026-11-16T17:32:23.529728+00:00')
        journal.write_text(json.dumps(record));closed=journal.read_bytes()
        if not restart:verify(client)
    if restart:
        with TestClient(create_app(settings)) as client:
            client.app.state.camera.adapter.driver.transport=wire;connect(client,b)
            verify(client)
