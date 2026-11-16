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
from test_sony_ptp import FakeWia, driver
from test_sony_zve10 import settings
from test_sessions import create, headers, key


def pending(tmp_path):
    camera,wire=driver(tmp_path);capture_id=str(uuid.uuid4())
    camera.capture_photo(capture_id,time.monotonic()+5)
    return camera,wire,capture_id


def test_cancel_preserves_receipt_blocks_old_key_and_allows_new_capture(tmp_path):
    camera,wire,capture_id=pending(tmp_path)
    wire.photos.clear()  # Simulates failed exposure with an empty camera buffer.
    journal,_=camera._paths(capture_id);before=journal.read_bytes();shots=wire.shots
    camera.cancel_capture(capture_id,time.monotonic()+5,confirm_discard=True)
    assert wire.shots==shots and not camera.unresolved
    assert (camera.root/'cancelled'/journal.name).read_bytes()==before
    assert json.loads(journal.read_text())['status']=='cancelled'
    camera.disconnect();camera.connect()
    with pytest.raises(CameraError) as caught:camera.capture_photo(capture_id,time.monotonic()+5)
    assert caught.value.code=='capture_cancelled' and wire.shots==shots
    camera.capture_photo(str(uuid.uuid4()),time.monotonic()+5)
    assert wire.shots==shots+1


@pytest.mark.parametrize('unsafe',['no_confirmation','buffer_has_image','release_pending','metadata','cached_jpeg'])
def test_unsafe_cancellation_is_refused_without_touching_records(tmp_path,unsafe):
    camera,wire,capture_id=pending(tmp_path)
    journal,saved=camera._paths(capture_id)
    if unsafe!='buffer_has_image':wire.photos.clear()
    record=json.loads(journal.read_text())
    if unsafe=='release_pending':record['release_pending']=True
    if unsafe=='metadata':record['object']={'size':100}
    journal.write_text(json.dumps(record))
    if unsafe=='cached_jpeg':saved.write_bytes(b'preserve this fixture')
    before=journal.read_bytes();shots=wire.shots
    with pytest.raises(CameraError):camera.cancel_capture(capture_id,time.monotonic()+5,confirm_discard=unsafe!='no_confirmation')
    assert journal.read_bytes()==before and wire.shots==shots
    assert not (camera.root/'cancelled').exists()
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
        sid=create(client);base=f'/api/sessions/{sid}/camera'
        assert client.post(base+'/connect',headers=headers()).status_code==200
        def missing_photo(*args,**kwargs):raise CameraError('timeout','TEST no JPEG arrived',stage='transfer')
        monkeypatch.setattr(camera.adapter.driver,'get_captured_photo',missing_photo)
        response=client.post(base+'/captures',headers=headers(key()),json={'slot_index':0})
        assert response.status_code==504
        with camera.repo.db.connect() as db:
            capture_id=db.execute('SELECT id FROM camera_captures').fetchone()[0]
        original_paths={p:p.read_bytes() for p in settings.storage_root.rglob('*.jpg')}
    wire.photos.clear()
    monkeypatch.setattr(cli,'SonyPtpDriver',lambda storage,timeout:SonyPtpDriver(storage,timeout,transport=wire))
    shots=wire.shots
    result=cli.cancel(settings.storage_root,capture_id,confirm_discard=True)
    assert result['status']=='cancelled' and Path(result['receipt_archive']).is_file()
    assert cli.cancel(settings.storage_root,capture_id,confirm_discard=True)['status']=='already_cancelled'
    assert wire.shots==shots and all(p.read_bytes()==data for p,data in original_paths.items())
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera
        with camera.repo.db.connect() as db:
            row=db.execute('SELECT * FROM camera_captures').fetchone()
        assert row['error_code']=='capture_cancelled' and row['status']=='failed' and not row['uncertain']
        with pytest.raises(CameraError) as caught:camera._capture_replay(row,sid,'a'*64,0)
        assert caught.value.code=='capture_cancelled'
