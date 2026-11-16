"""Deterministic controller concurrency tests; no physical camera access."""
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.camera.base import CameraError
from test_camera import settings, connect
from test_sessions import create


def test_slow_frame_does_not_block_status_or_accept_released_session(settings,monkeypatch):
    with TestClient(create_app(settings)) as client:
        sid=create(client);connect(client,sid)
        camera=client.app.state.camera;original=camera.adapter.get_preview_frame
        frame=original();entered=threading.Event();release=threading.Event()
        def slow_frame():
            entered.set();assert release.wait(5);return frame
        monkeypatch.setattr(camera.adapter,'get_preview_frame',slow_frame)
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending=pool.submit(camera.frame,sid,'a'*64)
            try:
                assert entered.wait(2)
                status=pool.submit(camera.status).result(timeout=1)
                assert status['connected']
                camera.disconnect(sid,'a'*64)
                release.set()
                with pytest.raises(CameraError) as caught:pending.result(timeout=2)
                assert caught.value.code=='not_connected'
                assert camera.owner is None and camera.state=='disconnected'
            finally:release.set()


def test_capture_has_priority_and_duplicate_frames_do_not_refresh_health(settings,monkeypatch):
    with TestClient(create_app(settings)) as client:
        sid=create(client);connect(client,sid)
        camera=client.app.state.camera;frame=camera.adapter.get_preview_frame();calls=[]
        monkeypatch.setattr(camera.adapter,'get_preview_frame',lambda:calls.append(1) or frame)
        with camera.capture_lock:
            with pytest.raises(CameraError) as caught:camera.frame(sid,'a'*64)
            assert caught.value.code=='busy' and not calls
        assert camera.frame(sid,'a'*64).sequence==frame.sequence
        before=camera.last_frame_at
        with pytest.raises(CameraError) as caught:camera.frame(sid,'a'*64)
        assert caught.value.code=='preview_pending' and camera.last_frame_at==before
        assert camera.preview_performance()['samples']>=1


def test_preview_metrics_are_bounded_and_include_validated_sony_timings(settings):
    with TestClient(create_app(settings)) as client:
        sid=create(client);connect(client,sid)
        camera=client.app.state.camera
        for i in range(150):
            camera.preview_samples.append({'at':float(i),'processing_ms':10.,'lock_ms':0.,'age_ms':2.,'acquisition_ms':8.})
        result=camera.status()['preview_performance']
        assert result['samples']==120 and result['delivered_fps']==1.
        assert result['acquisition_ms']=={'p50':8.,'p95':8.,'max':8.}
