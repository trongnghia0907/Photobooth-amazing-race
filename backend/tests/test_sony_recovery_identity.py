"""Recovery identity is evidence-bound; all USB commands use FakeWia."""
import hashlib
import json
import time
import uuid

import pytest
from app.services.camera.base import CameraError
from app.services.camera.sony_ptp import SonyPtpDriver
from test_sony_ptp import driver, jpeg
from test_sony_mpo import MpoCamera, seed_rejected


def interrupted(tmp_path):
    camera,wire=driver(tmp_path);end=time.monotonic()+5
    reference=camera.capture_photo(str(uuid.uuid4()),end)
    wire.fault='transfer_timeout'
    with pytest.raises(CameraError):camera.get_captured_photo(reference,end)
    camera.connect()
    return camera,wire,reference,end


def test_identical_objectinfo_cannot_prove_identity_after_uncertain_getobject(tmp_path):
    camera,wire,reference,end=interrupted(tmp_path)
    original,sequence=wire.photos[0]
    # Same metadata, same byte length, different decodable image.
    other=jpeg('blue');size=max(len(original),len(other))
    journal,_=camera._paths(reference);record=json.loads(journal.read_text())
    record['object']['size']=size;journal.write_text(json.dumps(record))
    wire.photos=[(other+b'\0'*(size-len(other)),sequence)]
    before=len([c for c in wire.commands if c[0]==0x1009])
    with pytest.raises(CameraError,match='[Kk]hông.*chứng minh|chưa.*xác minh'):
        camera.get_captured_photo(reference,end)
    assert len([c for c in wire.commands if c[0]==0x1009])==before
    assert wire.shots==1 and wire.photos


def test_local_verified_original_wins_over_changed_usb_buffer_and_restart(tmp_path):
    camera,wire=driver(tmp_path);end=time.monotonic()+5
    reference=camera.capture_photo(str(uuid.uuid4()),end)
    original=camera.get_captured_photo(reference,end).data;camera.disconnect()
    restarted=SonyPtpDriver(tmp_path,transport=wire);restarted.connect()
    wire.photos=[(jpeg('yellow'),999)];commands=len(wire.commands)
    for _ in range(3):assert restarted.get_captured_photo(reference,end).data==original
    assert len(wire.commands)==commands and wire.shots==1 and wire.photos


def test_legacy_cache_without_a_checksum_is_not_silently_trusted(tmp_path):
    camera,wire,reference,end=interrupted(tmp_path)
    journal,saved=camera._paths(reference);record=json.loads(journal.read_text())
    record.pop('sha256',None);record.pop('received_sha256',None);journal.write_text(json.dumps(record))
    saved.write_bytes(wire.photos[0][0]);before=saved.read_bytes();commands=len(wire.commands)
    with pytest.raises(CameraError):camera.get_captured_photo(reference,end)
    assert saved.read_bytes()==before and len(wire.commands)==commands


def test_changed_metadata_is_preserved_and_no_wrong_buffer_is_consumed(tmp_path):
    camera,wire,reference,end=interrupted(tmp_path)
    wire.photos=[(jpeg('yellow'),999)]
    for _ in range(2):
        with pytest.raises(CameraError,match='buffer changed'):camera.get_captured_photo(reference,end)
    journal,_=camera._paths(reference);record=json.loads(journal.read_text())
    evidence=record['identity_conflict']
    assert evidence['expected']['name']!=evidence['observed']['name']
    assert 'name' in evidence['changed_fields']
    assert wire.photos and wire.shots==1


@pytest.mark.parametrize('restart',[False,True])
def test_optional_dimensions_change_requires_hash_and_actual_jpeg_match(tmp_path,restart):
    camera,wire,reference,end=interrupted(tmp_path)
    original=wire.photos[0][0];journal,_=camera._paths(reference)
    record=json.loads(journal.read_text());record['object'].update(width=0,height=0)
    record['received_sha256']=hashlib.sha256(original).hexdigest();journal.write_text(json.dumps(record))
    if restart:
        camera.disconnect();camera=SonyPtpDriver(tmp_path,transport=wire);camera.connect()
    assert camera.get_captured_photo(reference,end).data==original
    assert wire.shots==1


@pytest.mark.parametrize('field,value',[('name','OTHER.JPG'),('size',123456),('format',0x3000),('sequence',999)])
def test_changed_non_geometry_fields_stay_blocked_even_with_known_hash(tmp_path,monkeypatch,field,value):
    from app.services.camera import sony_ptp
    camera,wire,reference,end=interrupted(tmp_path);journal,_=camera._paths(reference)
    record=json.loads(journal.read_text());record['received_sha256']=hashlib.sha256(wire.photos[0][0]).hexdigest()
    journal.write_text(json.dumps(record));parse=sony_ptp.object_info
    monkeypatch.setattr(sony_ptp,'object_info',lambda data:{**parse(data),field:value})
    before=len(wire.commands)
    with pytest.raises(CameraError):camera.get_captured_photo(reference,end)
    assert not any(op==0x1009 for op,_params,_data in wire.commands[before:])
    assert field in json.loads(journal.read_text())['identity_conflict']['changed_fields']
    assert wire.shots==1 and wire.photos


def test_known_hash_rejects_different_bytes_even_when_metadata_matches(tmp_path):
    camera,wire,reference,end=interrupted(tmp_path)
    original,sequence=wire.photos[0];other=jpeg('blue');size=max(len(original),len(other))
    original+=b'\0'*(size-len(original));other+=b'\0'*(size-len(other))
    journal,saved=camera._paths(reference);record=json.loads(journal.read_text())
    record['object']['size']=size;record['received_sha256']=hashlib.sha256(original).hexdigest()
    journal.write_text(json.dumps(record));wire.photos=[(other,sequence)]
    with pytest.raises(CameraError):camera.get_captured_photo(reference,end)
    assert not saved.exists() and wire.shots==1
    record=json.loads(journal.read_text());evidence=record['unexpected_transfer']
    assert (tmp_path/evidence['path']).read_bytes()==other
    assert evidence['sha256']!=record['received_sha256']


def test_rejected_payload_conflicting_with_existing_identity_is_not_cached(tmp_path):
    wire=MpoCamera();camera=SonyPtpDriver(tmp_path,transport=wire);camera.connect();end=time.monotonic()+5
    reference=camera.capture_photo(str(uuid.uuid4()),end)
    retained=seed_rejected(camera,wire,reference,wire.original)
    journal,_=camera._paths(reference);record=json.loads(journal.read_text());record['sha256']='0'*64
    journal.write_text(json.dumps(record));commands=len(wire.commands)
    with pytest.raises(CameraError):camera.get_captured_photo(reference,end)
    assert reference not in camera.transfer_cache and len(wire.commands)==commands
    assert retained.read_bytes()==wire.original


@pytest.mark.parametrize('restart',[False,True])
def test_old_intent_without_object_or_hash_is_not_rebound_after_connection_loss(tmp_path,restart):
    camera,wire=driver(tmp_path);end=time.monotonic()+5
    reference=camera.capture_photo(str(uuid.uuid4()),end)
    camera.disconnect()
    if restart:camera=SonyPtpDriver(tmp_path,transport=wire)
    camera.connect();wire.photos=[(jpeg('blue'),999)];before=len(wire.commands)
    with pytest.raises(CameraError):camera.get_captured_photo(reference,end)
    assert not any(op==0x1009 for op,_params,_data in wire.commands[before:])
    assert wire.shots==1 and wire.photos


@pytest.mark.parametrize('restart',[False,True])
def test_hash_checkpoint_disk_failure_keeps_consumed_bytes_in_memory(tmp_path,monkeypatch,restart):
    from app.services.camera import sony_ptp
    camera,wire=driver(tmp_path);end=time.monotonic()+5
    reference=camera.capture_photo(str(uuid.uuid4()),end);original=wire.photos[0][0]
    write=sony_ptp.atomic_write
    def fail_checkpoint(path,payload):
        if path.suffix=='.json' and b'received_sha256' in payload:raise OSError('TEST checkpoint fsync failed')
        return write(path,payload)
    monkeypatch.setattr(sony_ptp,'atomic_write',fail_checkpoint)
    with pytest.raises(OSError):camera.get_captured_photo(reference,end)
    assert camera.transfer_cache[reference]==original and not wire.photos and wire.shots==1
    # Once local storage recovers, the retained, capture-bound original must be
    # saved without reading another buffer or sending another shutter.
    monkeypatch.setattr(sony_ptp,'atomic_write',write)
    camera.disconnect()
    if restart:camera=SonyPtpDriver(tmp_path,transport=wire)
    camera.connect()
    if restart:
        # A process restart loses the RAM-only proof. Never substitute a new
        # buffer merely because the old checksum could not reach the disk.
        wire.photos=[(jpeg('blue'),999)];before=len(wire.commands)
        with pytest.raises(CameraError):camera.get_captured_photo(reference,end)
        assert wire.shots==1 and wire.photos and not camera._paths(reference)[1].exists()
        assert not any(op in (0x1009,0x9207) for op,_params,_data in wire.commands[before:])
        return
    before=len(wire.commands)
    assert camera.get_captured_photo(reference,end).data==original
    journal,saved=camera._paths(reference)
    assert saved.read_bytes()==original
    assert json.loads(journal.read_text())['sha256']==hashlib.sha256(original).hexdigest()
    assert wire.commands[before:]==[(0x9209,(),None)] and wire.shots==1
    assert json.loads(journal.read_text())['buffer_drained']
    assert reference not in camera.transfer_cache and reference not in camera.transfer_hashes


@pytest.mark.parametrize('missing_identity',[False,True])
def test_checkpoint_retry_refuses_changed_or_unbound_ram_bytes(tmp_path,monkeypatch,missing_identity):
    from app.services.camera import sony_ptp
    camera,wire=driver(tmp_path);end=time.monotonic()+5
    reference=camera.capture_photo(str(uuid.uuid4()),end)
    write=sony_ptp.atomic_write
    def fail_checkpoint(path,payload):
        if path.suffix=='.json' and b'received_sha256' in payload:raise OSError('TEST checkpoint fsync failed')
        return write(path,payload)
    monkeypatch.setattr(sony_ptp,'atomic_write',fail_checkpoint)
    with pytest.raises(OSError):camera.get_captured_photo(reference,end)
    monkeypatch.setattr(sony_ptp,'atomic_write',write)
    if missing_identity:camera.transfer_hashes.pop(reference)
    else:camera.transfer_cache[reference]=jpeg('blue')
    journal,saved=camera._paths(reference);receipt=journal.read_bytes();before=len(wire.commands)
    with pytest.raises(CameraError):camera.get_captured_photo(reference,end)
    assert journal.read_bytes()==receipt and not saved.exists()
    assert len(wire.commands)==before and wire.shots==1
    assert reference in camera.transfer_cache
