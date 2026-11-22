"""Explicit cancellation of empty captures only; no physical hardware."""
import importlib.util
import json
from pathlib import Path
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.runtime_lock import RuntimeLock
from app.services.camera.base import CameraError
from app.services.camera.sony_ptp import SonyPtpDriver
from test_sony_ptp import FakeWia, HALF_RELEASE, driver, jpeg
from test_sony_zve10 import capture, connect, settings
from test_sessions import create, headers, key


def pending(tmp_path):
    camera,wire=driver(tmp_path);capture_id=str(uuid.uuid4())
    camera.capture_photo(capture_id,time.monotonic()+5)
    return camera,wire,capture_id


def test_abandonment_keeps_guard_for_jpeg_that_could_arrive_after_preflight(tmp_path):
    camera,wire,capture_id=pending(tmp_path)
    wire.photos.clear()  # Simulates failed exposure with an empty camera buffer.
    journal,_=camera._paths(capture_id);before=journal.read_bytes();shots=wire.shots
    decision=camera.cancel_capture(capture_id,time.monotonic()+5,confirm_discard=True)
    assert wire.shots==shots and journal in camera.unresolved
    assert (camera.root/'abandonment'/journal.name).read_bytes()==before
    assert decision['status']=='dispatched' and decision['physical_outcome']=='uncertain'
    camera.disconnect();camera.connect()
    assert camera.cancel_capture(capture_id,time.monotonic()+5,confirm_discard=True)==decision
    with pytest.raises(CameraError) as caught:camera.capture_photo(str(uuid.uuid4()),time.monotonic()+5)
    assert caught.value.code=='recovery_required' and wire.shots==shots


@pytest.mark.parametrize('unsafe',['no_confirmation','buffer_has_image','release_pending','half_release_pending','metadata','cached_jpeg','hash','attempted'])
def test_unsafe_cancellation_is_refused_without_touching_records(tmp_path,unsafe):
    camera,wire,capture_id=pending(tmp_path)
    journal,saved=camera._paths(capture_id)
    if unsafe!='buffer_has_image':wire.photos.clear()
    record=json.loads(journal.read_text())
    if unsafe=='release_pending':record['release_pending']=True
    if unsafe=='half_release_pending':record['half_release_pending']=True
    if unsafe=='metadata':record['object']={'size':100}
    if unsafe=='hash':record['received_sha256']='a'*64
    if unsafe=='attempted':record['transfer_attempted']=True
    journal.write_text(json.dumps(record))
    if unsafe=='cached_jpeg':saved.write_bytes(b'preserve this fixture')
    before=journal.read_bytes();shots=wire.shots
    with pytest.raises(CameraError):camera.cancel_capture(capture_id,time.monotonic()+5,confirm_discard=unsafe!='no_confirmation')
    assert journal.read_bytes()==before and wire.shots==shots
    assert not (camera.root/'abandonment').exists()
    if unsafe=='cached_jpeg':assert saved.read_bytes()==b'preserve this fixture'


def load_cli():
    path=Path(__file__).resolve().parents[2]/'scripts/cancel_sony_capture.py'
    spec=importlib.util.spec_from_file_location('sony_cancel_cli',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_cli_refuses_running_host(settings):
    cli=load_cli()
    with TestClient(create_app(settings)):
        lease=RuntimeLock(settings.storage_root/'.host-app.lock').acquire()
        try:
            with pytest.raises(RuntimeError,match='Stop the Photobooth Host'):
                cli.cancel(settings.storage_root,None,confirm_discard=True)
        finally:lease.close()


def test_cli_refuses_an_existing_camera_controller(settings):
    cli=load_cli()
    with TestClient(create_app(settings)):
        lease=RuntimeLock(settings.storage_root/'.camera-controller.lock').acquire()
        try:
            with pytest.raises(RuntimeError,match='camera controller still owns'):
                cli.cancel(settings.storage_root,None,confirm_discard=True)
        finally:lease.close()


def test_cli_camera_busy_changes_no_capture_records(settings,monkeypatch):
    cli=load_cli();wire=FakeWia()
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        sid=create(client);base=f'/api/sessions/{sid}/camera'
        assert client.post(base+'/connect',headers=headers()).status_code==200
        def missing(*args):raise CameraError('timeout','TEST no JPEG',stage='transfer')
        monkeypatch.setattr(camera.adapter.driver,'get_captured_photo',missing)
        client.post(base+'/captures',headers=headers(key()),json={'slot_index':0})
        with camera.repo.db.connect() as db:before=dict(db.execute('SELECT * FROM camera_captures').fetchone())
        journal=camera.adapter.driver._paths(before['id'])[0];raw=journal.read_bytes()
    def busy(deadline):raise CameraError('busy','TEST WIA_BUSY')
    wire.open=busy
    monkeypatch.setattr(cli,'SonyPtpDriver',lambda storage,timeout:SonyPtpDriver(storage,timeout,transport=wire))
    with pytest.raises(CameraError,match='WIA_BUSY'):
        cli.cancel(settings.storage_root,before['id'],confirm_discard=True)
    assert journal.read_bytes()==raw and not (journal.parent/'cancelled').exists()
    with TestClient(create_app(settings)) as client:
        with client.app.state.repository.db.connect() as db:after=dict(db.execute('SELECT * FROM camera_captures').fetchone())
    assert after==before


def test_cli_cancellation_is_persistent_idempotent_and_does_not_touch_photos(settings,monkeypatch):
    cli=load_cli();wire=FakeWia()
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        database=camera.repo.db
        sid=create(client);base=f'/api/sessions/{sid}/camera'
        assert client.post(base+'/connect',headers=headers()).status_code==200
        def missing_photo(*args,**kwargs):raise CameraError('timeout','TEST no JPEG arrived',stage='transfer')
        monkeypatch.setattr(camera.adapter.driver,'get_captured_photo',missing_photo)
        abandoned_key=key()
        response=client.post(base+'/captures',headers=headers(abandoned_key),json={'slot_index':0})
        assert response.status_code==504
        with camera.repo.db.connect() as db:
            capture_id=db.execute('SELECT id FROM camera_captures').fetchone()[0]
        original_paths={p:p.read_bytes() for p in settings.storage_root.rglob('*.jpg')}
    wire.photos.clear()
    monkeypatch.setattr(cli,'SonyPtpDriver',lambda storage,timeout:SonyPtpDriver(storage,timeout,transport=wire))
    shots=wire.shots
    result=cli.cancel(settings.storage_root,capture_id,confirm_discard=True)
    assert result['status']=='abandonment_pending' and Path(result['receipt_archive']).is_file()
    assert cli.cancel(settings.storage_root,capture_id,confirm_discard=True)==result
    assert wire.shots==shots and all(p.read_bytes()==data for p,data in original_paths.items())
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera
        with camera.repo.db.connect() as db:
            row=db.execute('SELECT * FROM camera_captures').fetchone()
        assert row['error_code']=='timeout' and row['status']=='transfer_failed'
        camera.adapter.driver.transport=wire
        successor=create(client)
        base=f'/api/sessions/{successor}/camera'
        assert client.post(base+'/connect',headers=headers()).json()['capture_readiness']=='reconciliation_required'
        before_commands=len(wire.commands)
        check=client.get(base+'/status?check_capture=true',headers=headers())
        assert check.status_code==503 and check.json()['error']['code']=='camera_recovery_pending'
        assert len(wire.commands)==before_commands
        blocked=client.post(base+'/captures',headers=headers(key()),json={'slot_index':0})
        assert blocked.json()['error']['code']=='camera_recovery_pending'
        assert blocked.json()['error']['shutter_dispatched'] is False and wire.shots==shots
    assert successor!=sid
    archive=Path(result['receipt_archive'])
    original=archive.read_bytes()
    journal=archive.parent.parent/archive.name
    before=journal.read_bytes()
    with database.connect() as db:
        db.execute("UPDATE camera_captures SET status='transferring' WHERE id=?",(capture_id,))
    with pytest.raises(RuntimeError,match='still active in the Host database'):
        cli.cancel(settings.storage_root,capture_id,confirm_discard=True,isolation_step='power_off')
    assert journal.read_bytes()==before
    with database.connect() as db:
        db.execute("UPDATE camera_captures SET status='failed' WHERE id=?",(capture_id,))
    healthy={'original_zv_e10_name_match':True,'pnp_status':'OK'}
    monkeypatch.setattr(cli,'probe_windows',lambda _:pnp)

    def isolate(step):
        return cli.cancel(settings.storage_root,capture_id,confirm_discard=True,isolation_step=step)

    pnp={'status':'QUERIED','devices':[healthy]}
    with pytest.raises(RuntimeError,match='still sees a Sony device'):
        isolate('power_off')
    with pytest.raises(CameraError,match='First record'):
        isolate('verify_reconnect')
    assert not json.loads(journal.read_bytes()).get('isolation_power_off_at')
    pnp={'status':'UNAVAILABLE','devices':[]}
    with pytest.raises(RuntimeError,match='Cannot verify Windows'):
        isolate('power_off')
    pnp={'status':'QUERIED','devices':[]}
    assert not wire.connected
    opened=wire.open_count
    recorded=isolate('power_off')
    assert recorded['status']=='power_off_recorded' and recorded['new_capture_blocked']
    assert isolate('power_off')==recorded and wire.open_count==opened

    pnp={'status':'QUERIED','devices':[{**healthy,'pnp_status':'Error'}]}
    with pytest.raises(RuntimeError,match='one healthy Sony'):
        isolate('verify_reconnect')
    assert wire.open_count==opened
    pnp={'status':'QUERIED','devices':[healthy]}
    with pytest.raises(CameraError,match='PC Only'):
        isolate('verify_reconnect')
    wire.destination=1
    wire.photos.append((jpeg('red'),1))  # Even here a late/unknown JPEG keeps the guard.
    with pytest.raises(CameraError,match='unclaimed image'):
        isolate('verify_reconnect')
    assert archive.read_bytes()==original and wire.shots==shots and len(wire.photos)==1
    assert json.loads(journal.read_bytes())['status']=='dispatched'

    wire.photos.clear()  # Fake volatile memory after a full power loss, with old media out.
    isolated=isolate('verify_reconnect')
    assert isolated['status']=='abandonment_isolated' and isolated['physical_outcome']=='uncertain'
    assert archive.read_bytes()==original and Path(isolated['receipt_archive']).read_bytes()==journal.read_bytes()
    assert isolate('verify_reconnect')=={'status':'already_cancelled'} and wire.shots==shots
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera
        camera.adapter.driver.transport=wire
        new_base=connect(client,successor)
        with camera.repo.db.connect() as db:
            old=db.execute('SELECT * FROM camera_captures WHERE id=?',(capture_id,)).fetchone()
        assert old['error_code']=='capture_cancelled' and old['uncertain']==1
        assert old['request_key']==abandoned_key and old['session_id']==sid
        assert client.get(new_base+'/status?check_capture=true',headers=headers()).status_code==200
        new_key=key()
        wire.photos.append((jpeg('red'),1))  # An unexpected occupied buffer still prevents shutter.
        rejected=capture(client,new_base,0,new_key)
        assert rejected.json()['error']['shutter_dispatched'] is False and wire.shots==shots
        assert len(wire.photos)==1
        wire.photos.clear()
        saved=capture(client,new_base,0,new_key)
        assert saved.status_code==200 and wire.shots==shots+1
        assert capture(client,new_base,0,new_key).json()==saved.json() and wire.shots==shots+1
        with camera.repo.db.connect() as db:
            new=db.execute('SELECT * FROM camera_captures WHERE request_key=?',(new_key,)).fetchone()
        assert new['id']!=capture_id and new['session_id']==successor and new['status']=='captured'
        assert (settings.storage_root/new['native_path']).read_bytes()==jpeg('green')
        assert archive.read_bytes()==original


def test_proven_preflight_failure_does_not_leave_a_pending_capture(settings):
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;wire=FakeWia();camera.adapter.driver.transport=wire
        first=create(client);base=connect(client,first)
        wire.drive=2
        error=capture(client,base,0).json()['error']
        assert error['code']=='camera_mode' and error['clear_pending']
        assert error['shutter_dispatched'] is False and wire.shots==0
        assert not camera.adapter.driver.unresolved
        assert client.post(base+'/disconnect',headers=headers()).status_code==200
        wire.drive=1
        next_base=connect(client,create(client))
        assert capture(client,next_base,0).status_code==200 and wire.shots==1


def test_failed_half_press_releases_only_half_and_retires_before_new_shutter(settings,monkeypatch):
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;wire=FakeWia();camera.adapter.driver.transport=wire
        base=connect(client,create(client));operation=key()
        command=wire.command

        def fail_half_press(opcode,params=(),**kwargs):
            if opcode==0x9207 and params==(HALF_RELEASE,) and kwargs['data']==b'\x02\x00':
                raise CameraError('busy','TEST half-press acknowledgment failed')
            return command(opcode,params,**kwargs)

        monkeypatch.setattr(wire,'command',fail_half_press)
        failed=capture(client,base,0,operation).json()['error']
        assert failed['shutter_dispatched'] is False and wire.shots==0
        assert camera.adapter.driver.unresolved
        assert client.post(base+'/disconnect',headers=headers()).status_code==200
        successor=connect(client,create(client))
        monkeypatch.setattr(wire,'command',command)
        wire.photos.append((jpeg('purple'),999))
        offset=len(wire.commands)
        blocked=capture(client,successor,0).json()['error']
        assert blocked['code']=='camera_recovery_pending' and wire.shots==0
        assert [command for command in wire.commands[offset:] if command[0]==0x9207]==[(0x9207,(HALF_RELEASE,),b'\x01\x00')]
        assert len(wire.photos)==1
        wire.photos.clear()
        assert capture(client,successor,0).status_code==200 and wire.shots==1
        assert not camera.adapter.driver.unresolved


def test_recovery_only_cannot_dispatch_a_shutter_without_a_receipt(settings):
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;wire=FakeWia();camera.adapter.driver.transport=wire
        sid=create(client);base=connect(client,sid)
        operation=key()
        def retry():
            return client.post(base+'/captures',headers=headers(operation),json={'slot_index':0,'recovery_only':True})
        assert retry().json()['error']['code']=='capture_not_found'
        wire.drive=2
        assert capture(client,base,0,operation).json()['error']['code']=='camera_mode'
        wire.drive=1
        refused=retry()
        assert refused.json()['error']['shutter_dispatched'] is False and wire.shots==0
        saved=capture(client,base,0,operation)
        assert saved.status_code==200 and wire.shots==1
        assert retry().json()==saved.json() and wire.shots==1
