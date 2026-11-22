"""Deterministic controller concurrency tests; no physical camera access."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

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
        frame=original();entered=threading.Event();release=threading.Event();reserved=threading.Event()
        original_reserve=camera._reserve_transition
        def reserve(*args):
            original_reserve(*args);reserved.set()
        def slow_frame():
            entered.set();assert release.wait(5);return frame
        monkeypatch.setattr(camera.adapter,'get_preview_frame',slow_frame)
        monkeypatch.setattr(camera,'_reserve_transition',reserve)
        with ThreadPoolExecutor(max_workers=3) as pool:
            pending=pool.submit(camera.frame,sid,'a'*64)
            try:
                assert entered.wait(2)
                closing=pool.submit(camera.disconnect,sid,'a'*64)
                assert reserved.wait(2)
                status=pool.submit(camera.status).result(timeout=1)
                assert status['connected'] and status['lease_active'] and not closing.done()
                with pytest.raises(CameraError) as busy:camera.frame(sid,'a'*64)
                assert busy.value.code=='busy'
                release.set()
                with pytest.raises(CameraError) as caught:pending.result(timeout=2)
                assert caught.value.code=='not_connected'
                assert closing.result(timeout=2)=={'state':'disconnected'}
                assert camera.owner is None and camera.state=='disconnected'
            finally:release.set()


def test_lease_monitor_retries_cleanup_after_frame_and_close_fail(settings,monkeypatch):
    with TestClient(create_app(settings)) as client:
        sid=create(client);other=create(client);connect(client,sid)
        camera=client.app.state.camera;adapter=camera.adapter
        entered,release,failed,allow_close,released=(threading.Event() for _ in range(5))
        close=adapter.disconnect
        def frame():
            entered.set();assert release.wait(5)
            raise CameraError('transport_failed','TEST frame failed')
        def disconnect():
            if not allow_close.is_set():
                failed.set()
                raise CameraError('worker_stalled','TEST worker still owns camera')
            close()
            released.set()
        monkeypatch.setattr(adapter,'get_preview_frame',frame)
        monkeypatch.setattr(adapter,'disconnect',disconnect)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(camera.frame,sid,'a'*64)
            try:
                assert entered.wait(2)
                camera.lease_until=time.monotonic()-1
                assert camera.status()['lease_active'] and not failed.is_set()
                release.set()
                with pytest.raises(CameraError,match='TEST frame failed'):pending.result(timeout=2)
                assert failed.wait(2)
                assert camera.owner==sid and camera.thread.is_alive()
                with pytest.raises(CameraError,match='phiên khác|đang đóng phiên'):
                    camera.connect(other,'a'*64)
                allow_close.set()
                assert released.wait(2)
            finally:
                release.set();allow_close.set()
        with camera.control:assert not adapter.connected


def test_stop_drains_admitted_capture_and_releases_process_lease(settings,monkeypatch):
    with TestClient(create_app(settings)) as client:
        sid=create(client);connect(client,sid);camera=client.app.state.camera
        entered=threading.Event();release=threading.Event()
        trigger=camera.adapter.capture_photo
        def capture(capture_id,deadline):
            entered.set();assert release.wait(5);return trigger(capture_id,deadline)
        monkeypatch.setattr(camera.adapter,'capture_photo',capture)
        with ThreadPoolExecutor(max_workers=2) as pool:
            shot=pool.submit(camera.capture,sid,'a'*64,'request-key-1234',0)
            try:
                assert entered.wait(2)
                shutdown=pool.submit(camera.stop)
                assert camera.stop_event.wait(2)
                assert not shutdown.done() and camera.process_lock is not None
                with pytest.raises(CameraError,match='Host đang dừng'):camera.frame(sid,'a'*64)
                release.set()
                assert shot.result(timeout=3)['capture']['status']=='captured'
                shutdown.result(timeout=3)
            finally:release.set()
        assert camera.process_lock is None and camera.owner is None
        assert not camera.adapter.connected and not camera.thread.is_alive()


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
