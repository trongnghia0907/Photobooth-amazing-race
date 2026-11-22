"""Session/test-boundary reconciliation; synthetic WIA and tmp_path only."""
import hashlib
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.camera.base import CameraError
from app.services.camera.sony_ptp import SonyPtpDriver
from test_sony_ptp import driver, FakeWia, jpeg
from test_sony_zve10 import settings, connect, capture
from test_sessions import create, headers, key, composite
from test_sony_diagnostic import diagnostic


def interrupted(camera, wire):
    identifier=str(uuid.uuid4())
    camera.capture_photo(identifier,time.monotonic()+5)
    wire.fault='transfer_timeout'
    with pytest.raises(CameraError):camera.get_captured_photo(identifier,time.monotonic()+5)
    camera.connect()  # A timed-out WIA root is closed; preflight requires ownership again.
    return identifier


@pytest.mark.parametrize('restart',[False,True])
def test_orphan_test_original_is_recovered_under_original_identity(tmp_path,restart):
    camera,wire=driver(tmp_path);cid=interrupted(camera,wire)
    original=wire.photos[0][0];journal,_=camera._paths(cid)
    record=json.loads(journal.read_text());record['received_sha256']=hashlib.sha256(original).hexdigest()
    journal.write_text(json.dumps(record));before=journal.read_bytes()
    if restart:
        camera.disconnect();camera=SonyPtpDriver(tmp_path,transport=wire);camera.connect()
    successor=str(uuid.uuid4());shots=wire.shots
    result=camera.reconcile_previous_captures(successor,time.monotonic()+5)
    assert result[0]['capture_id']==cid and wire.shots==shots
    assert (tmp_path/result[0]['original']['path']).read_bytes()==original
    assert (camera.root/'superseded'/journal.name).read_bytes()==before
    closed=journal.read_bytes()
    camera.reconcile_previous_captures(str(uuid.uuid4()),time.monotonic()+5)
    assert journal.read_bytes()==closed and wire.shots==shots


def test_consumed_transfer_is_retired_once_and_late_unknown_image_is_blocked(tmp_path):
    camera,wire=driver(tmp_path);cid=interrupted(camera,wire);wire.photos.clear()
    journal,_=camera._paths(cid);before=journal.read_bytes();shots=wire.shots
    camera.reconcile_previous_captures(str(uuid.uuid4()),time.monotonic()+5)
    assert json.loads(journal.read_text())['status']=='superseded'
    assert (camera.root/'superseded'/journal.name).read_bytes()==before
    wire.photos.append((jpeg('purple'),99))
    with pytest.raises(CameraError):camera.reconcile_previous_captures(str(uuid.uuid4()),time.monotonic()+5)
    assert wire.photos[0][1]==99 and wire.shots==shots


@pytest.mark.parametrize('physical',['empty_unknown','busy','pending','late_jpeg'])
def test_unknown_physical_outcome_never_auto_cancels_or_sends_shutter(tmp_path,monkeypatch,physical):
    camera,wire=driver(tmp_path);cid=str(uuid.uuid4())
    camera.capture_photo(cid,time.monotonic()+5);wire.photos.clear()
    camera.disconnect();camera.connect()  # A previous run has no live acquisition context.
    if physical=='late_jpeg':wire.photos.append((jpeg('purple'),999))
    if physical in ('busy','pending'):
        properties=camera._properties
        def unavailable(deadline):
            if physical=='busy':raise CameraError('busy','FAKE physical busy')
            values=properties(deadline);values[0xd215]['value']=1;return values
        monkeypatch.setattr(camera,'_properties',unavailable)
    before=len(wire.commands)
    with pytest.raises(CameraError):camera.reconcile_previous_captures(str(uuid.uuid4()),time.monotonic()+5)
    record=json.loads(camera._paths(cid)[0].read_text())
    assert record['status']=='dispatched' and wire.shots==1
    assert not any(op==0x9207 for op,_params,_data in wire.commands[before:])
    assert not (camera.root/'cancelled').exists()


@pytest.mark.parametrize('restart',[False,True])
def test_new_session_replays_cancel_receipt_database_crash_safely(settings,monkeypatch,restart):
    wire=FakeWia();operation=key()
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        a=create(client);base=connect(client,a);wire.fault='transfer_timeout'
        assert capture(client,base,0,operation).status_code!=200
        with camera.repo.db.connect() as db:
            row=db.execute('SELECT * FROM camera_captures WHERE session_id=?',(a,)).fetchone();cid=row['id']
        journal,_=camera.adapter.driver._paths(cid)
        # Simulate an already safely authorized cancellation, then a crash
        # before the SQLite ACK. No real camera or operator data is involved.
        record=json.loads(journal.read_text());record['object']=None
        journal.write_text(json.dumps(record));wire.photos.clear()
        camera.adapter.driver.connect()
        # Fixture for receipts written before abandonment remained unresolved.
        archive=journal.parent/'cancelled'/journal.name
        archive.parent.mkdir(parents=True,exist_ok=True)
        archive.write_bytes(journal.read_bytes())
        record.update(status='cancelled',cancel_reason='Legacy operator cancellation')
        journal.write_text(json.dumps(record))
        camera.adapter.driver.unresolved.discard(journal)
        if not restart:
            camera._reconcile_cancelled_receipts()
            first=None
            with camera.repo.db.connect() as db:first=dict(db.execute('SELECT * FROM camera_captures WHERE id=?',(cid,)).fetchone())
            camera._reconcile_cancelled_receipts()
            with camera.repo.db.connect() as db:assert dict(db.execute('SELECT * FROM camera_captures WHERE id=?',(cid,)).fetchone())==first
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        b=create(client);base_b=connect(client,b)
        with camera.repo.db.connect() as db:
            row=db.execute('SELECT * FROM camera_captures WHERE id=?',(cid,)).fetchone()
            assert row['status']=='failed' and row['error_code']=='capture_cancelled' and not row['uncertain']
        assert capture(client,base_b,0).status_code==200
        assert capture(client,base,0,operation).json()['error']['code']=='capture_cancelled'
        assert wire.shots==2 and (journal.parent/'cancelled'/journal.name).is_file()


def test_host_reconciles_orphan_receipt_before_new_shutter(settings):
    wire=FakeWia()
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;device=camera.adapter.driver;device.transport=wire
        sid=create(client);base=connect(client,sid)
        cid=interrupted(device,wire);original=wire.photos[0][0]
        journal,_=device._paths(cid);record=json.loads(journal.read_text())
        record['received_sha256']=hashlib.sha256(original).hexdigest();journal.write_text(json.dumps(record))
        assert capture(client,base,0).status_code==200
        assert (settings.storage_root/'camera_originals'/cid/(cid+'.jpg')).read_bytes()==original
        with camera.repo.db.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM camera_captures WHERE id=?',(cid,)).fetchone()[0]==0
        assert wire.shots==2


def test_independent_diagnostic_reuses_guard_before_any_new_shutter(tmp_path,monkeypatch):
    from app.services.camera.sony_zve10 import SonyZvE10CameraAdapter
    wire=FakeWia();wire.fault='transfer_timeout'
    def adapter(**kwargs):
        value=SonyZvE10CameraAdapter(**kwargs);value.driver.transport=wire;return value
    monkeypatch.setattr(diagnostic,'SonyZvE10CameraAdapter',adapter)
    monkeypatch.setattr(diagnostic,'probe_windows',lambda timeout:{'status':'QUERIED','devices':[]})
    first=diagnostic.diagnostic(capture=True,output_dir=tmp_path)
    assert first['camera_access']=='FAILED' and wire.shots==1
    second=diagnostic.diagnostic(capture=True,output_dir=tmp_path)
    assert second['camera_access']=='FAILED' and wire.shots==1
    assert second['protocol_checks']['stale_capture_preflight']=='FAIL'
    assert wire.photos and not wire.connected


def test_orphan_scan_runs_once_per_connected_session_not_preview_or_shot(settings,monkeypatch):
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;device=camera.adapter.driver;wire=FakeWia();device.transport=wire
        original=device.reconcile_previous_captures;calls=[]
        def observed(*args,**kwargs):calls.append(args[0]);return original(*args,**kwargs)
        monkeypatch.setattr(device,'reconcile_previous_captures',observed)
        sid=create(client);base=connect(client,sid)
        assert client.post(base+'/live-view/start',headers=headers()).status_code==200
        for _ in range(3):assert client.get(base+'/frame',headers=headers()).status_code==200
        assert calls==[]
        assert capture(client,base,0).status_code==200
        assert capture(client,base,1).status_code==200
        assert calls==[sid] and wire.shots==2


def test_completed_session_database_receipts_and_composite_are_unchanged(settings):
    wire=FakeWia()
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;device=camera.adapter.driver;device.transport=wire
        a=create(client,layout='landscape_4',slot_count=4);base=connect(client,a)
        for slot in range(4):
            response=capture(client,base,slot);assert response.status_code==200
        final=composite(client,a,response.json()['session']['shots_revision']).json()['composite']
        response=client.post(f'/api/sessions/{a}/complete',headers=headers(key()),json={'composite_id':final['id']})
        assert response.status_code==200,response.text
        with camera.repo.db.connect() as db:
            before=[dict(row) for row in db.execute('SELECT * FROM camera_captures WHERE session_id=?',(a,))]
            final_path=db.execute('SELECT path FROM composites WHERE id=?',(final['id'],)).fetchone()[0]
        payload=(settings.storage_root/final_path).read_bytes()
        receipts={path:path.read_bytes() for path in device.root.glob('*.json')}
        assert client.post(base+'/disconnect',headers=headers()).status_code==200
    with TestClient(create_app(settings)) as client:
        camera=client.app.state.camera;camera.adapter.driver.transport=wire
        b=create(client);base=connect(client,b)
        assert capture(client,base,0).status_code==200
        with camera.repo.db.connect() as db:
            assert [dict(row) for row in db.execute('SELECT * FROM camera_captures WHERE session_id=?',(a,))]==before
        assert (settings.storage_root/final_path).read_bytes()==payload
        assert all(path.read_bytes()==data for path,data in receipts.items())
