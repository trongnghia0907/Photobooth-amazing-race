import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.camera.base import CameraError
from app.services.camera.sony_ptp import HALF_RELEASE, SHUTTER_RELEASE
from test_sony_consecutive import driver
from test_sony_zve10 import settings, connect, capture
from test_sessions import create, headers, key


def test_focus_read_failure_releases_controls_without_repeating_shutter(tmp_path, monkeypatch):
    camera, wire = driver(tmp_path)
    wire.focus_mode = 0x8004
    identifier = str(uuid.uuid4())
    def focus_failure(deadline):
        raise CameraError('busy', 'Fixture focus property read failed')
    monkeypatch.setattr(camera, '_wait_focus', focus_failure)
    with pytest.raises(CameraError, match='focus property') as failure:
        camera.capture_photo(identifier, time.monotonic()+5)
    assert failure.value.shutter_dispatched is True and wire.shots == 1
    assert not wire.half and not wire.full
    assert wire.commands[-2:] == [
        (0x9207,(SHUTTER_RELEASE,),b'\1\0'),
        (0x9207,(HALF_RELEASE,),b'\1\0')]
    camera.recover_capture(identifier, time.monotonic()+5)
    assert camera.get_captured_photo(identifier, time.monotonic()+5).data == wire.originals[0]
    assert wire.shots == 1


def test_cache_cleanup_failure_after_commit_returns_saved_slot_and_allows_next(settings, monkeypatch):
    with TestClient(create_app(settings)) as client:
        camera = client.app.state.camera
        _, wire = driver(settings.storage_root)
        camera.adapter.driver.transport = wire
        sid = create(client)
        base = connect(client, sid)
        def cleanup_failure(_):
            raise OSError('Fixture cache unlink failed')
        monkeypatch.setattr(camera.adapter, 'capture_persisted', cleanup_failure)
        operation = key()
        first = capture(client, base, 0, operation)
        assert first.status_code == 200, first.text
        assert capture(client, base, 0, operation).json() == first.json()
        second = capture(client, base, 1)
        assert second.status_code == 200, second.text
        assert [photo['slot_index'] for photo in second.json()['session']['photos']] == [0,1]
        assert wire.shots == 2 and not camera.capture_lock.locked()
        assert client.get(base+'/frame', headers=headers()).status_code == 200
