"""Optional UVC DEMO: one native reader, bounded latest-frame buffers.
Preview JPEGs are scaled independently; captured frames keep native dimensions.
No physical shutter or original-camera-JPEG capability is claimed.
"""
import os
from pathlib import Path
import threading
import time
import uuid
from .base import CameraCapabilities, CameraError, CapturedPhoto, PreviewFrame
from ..images import atomic_write

_owners_lock = threading.Lock()
_owners = {}  # Also protects against replacing an adapter with a stuck reader.


class UvcDemoCameraAdapter:
    def __init__(self, root, index=0):
        self.root, self.index = Path(root), index
        self.device = self.thread = None
        self.connected = self.previewing = False
        self.sequence = 0
        self.delivered = -1
        self.condition = threading.Condition()
        self.lifecycle = threading.Lock()
        self.capture_lock = threading.Lock()
        self.stop, self.ready = threading.Event(), threading.Event()
        self.latest = self.preview = self.last_error = None
        self.read_started_at = None
        self.metrics = dict(read_ms=None, encode_ms=None, read_failures=0,
            consecutive_read_failures=0, encode_failures=0, opens=0, preview_fps=5,
            backend='DSHOW' if os.name == 'nt' else 'ANY')

    def get_capabilities(self):
        return CameraCapabilities('uvc_demo','Host UVC/webcam video-frame — DEMO',True,True,True,False,False,'webcam_frame')

    def get_status(self):
        with self.condition:
            age = (time.time()-self.latest[1])*1000 if self.latest else None
            return dict(connected=self.connected, previewing=self.previewing and self.connected,
                preview_diagnostics={**self.metrics, 'frame_age_ms':round(age,1) if age is not None else None,
                    'reader_running':bool(self.thread and self.thread.is_alive()), 'last_failure':self.last_error,
                    'read_in_progress_ms':round((time.monotonic()-self.read_started_at)*1000,1) if self.read_started_at else None})

    def connect(self):
        with self.lifecycle:
            if self.connected and not self.stop.is_set():return
            if self.thread and self.thread.is_alive():
                raise CameraError('worker_stalled','Webcam reader is still stopping. Restart Host if its native driver remains stuck; no second webcam will be opened.',stage='connect')
            try:import cv2
            except ImportError:
                raise CameraError('dependency_missing','UVC DEMO requires opencv-python (requirements-camera-optional.txt).',stage='connect') from None
            self.cv = cv2
            with _owners_lock:
                if self.index in _owners:
                    raise CameraError('worker_stalled','Another webcam reader still owns this device. Wait for cleanup or restart Host.',stage='connect')
                _owners[self.index] = self
            self.stop.clear();self.ready.clear()
            with self.condition:
                self.latest = self.preview = self.last_error = None
                self.delivered = -1
                self.metrics['consecutive_read_failures'] = 0
            self.thread = threading.Thread(target=self._read_frames,daemon=True,name='photobooth-uvc-reader')
            try:self.thread.start()
            except Exception:
                with _owners_lock:_owners.pop(self.index,None)
                raise
            if not self.ready.wait(5):
                self.stop.set()
                raise CameraError('worker_stalled','Webcam initialization timed out. The original reader must stop before reopening.',stage='connect')
            if not self.connected:
                raise CameraError('disconnected','Cannot open host webcam. Check device index, OS camera permission and other camera applications.',stage='connect')

    def _read_frames(self):
        device = None
        try:
            device = self.cv.VideoCapture(self.index,self.cv.CAP_DSHOW if os.name == 'nt' else self.cv.CAP_ANY)
            self.device = device
            if not device.isOpened():return
            # Best effort backend properties; never reduce native capture dimensions.
            for name,value in [('CAP_PROP_BUFFERSIZE',1),('CAP_PROP_FPS',15)]:
                prop = getattr(self.cv,name,None)
                if prop is not None:
                    try:device.set(prop,value)
                    except Exception:pass
            with self.condition:
                self.connected = True
                self.metrics['opens'] += 1
            self.ready.set()
            next_encode = 0
            while not self.stop.is_set():
                started = time.monotonic()
                self.read_started_at = started
                try:ok,frame = device.read()
                except Exception:ok,frame = False,None
                self.read_started_at = None
                if self.stop.is_set():break
                with self.condition:self.metrics['read_ms'] = round((time.monotonic()-started)*1000,1)
                if not ok or frame is None:
                    with self.condition:
                        self.metrics['read_failures'] += 1
                        failures = self.metrics['consecutive_read_failures'] = self.metrics['consecutive_read_failures']+1
                        opened = device.isOpened()
                        self.last_error = 'frame_read_failed' if opened else 'camera_not_open'
                        self.condition.notify_all()
                    if not opened or failures >= 5:break
                    self.stop.wait(min(0.05*2**(failures-1),0.4))
                    continue
                stamp = time.time()
                with self.condition:
                    self.sequence += 1
                    self.latest = (self.sequence,stamp,frame)
                    self.metrics['consecutive_read_failures'] = 0
                    if self.last_error=='frame_read_failed':self.last_error = None
                    self.condition.notify_all()
                if self.previewing and time.monotonic() >= next_encode:
                    encoded_at = time.monotonic()
                    try:
                        height,width = frame.shape[:2]
                        scale = min(1,960/width,720/height)
                        small = self.cv.resize(frame,(max(1,round(width*scale)),max(1,round(height*scale)))) if scale < 1 else frame
                        ok,data = self.cv.imencode('.jpg',small,[self.cv.IMWRITE_JPEG_QUALITY,75])
                        if not ok:raise ValueError('JPEG encoding failed')
                        with self.condition:
                            self.preview = PreviewFrame(data.tobytes(),self.sequence,stamp)
                            self.metrics['encode_ms'] = round((time.monotonic()-encoded_at)*1000,1)
                            self.last_error = None
                            self.condition.notify_all()
                    except Exception:
                        with self.condition:
                            self.metrics['encode_failures'] += 1
                            self.last_error = 'preview_encode_failed'
                    next_encode = time.monotonic()+0.2
                self.stop.wait(max(0,1/30-(time.monotonic()-started)))
        except Exception:
            with self.condition:self.last_error = 'camera_open_failed'
        finally:
            # Only this owner releases the camera, even if read() was stalled.
            released = True
            try:
                if device is not None:device.release()
            except Exception:
                released = False
                self.last_error = 'camera_release_failed'
            finally:
                with self.condition:
                    self.connected = self.previewing = False
                    self.device = None
                    self.condition.notify_all()
                self.ready.set()
                if released:
                    with _owners_lock:
                        if _owners.get(self.index) is self:_owners.pop(self.index,None)

    def disconnect(self):
        with self.lifecycle:
            self.stop.set()
            with self.condition:
                self.connected = self.previewing = False
                self.latest = self.preview = None
                self.condition.notify_all()
            if self.thread:self.thread.join(1)
            # Keep a stalled thread reference: connect cannot create another owner.

    def start_live_view(self):
        with self.condition:
            if not self.connected:raise CameraError('disconnected','Host webcam is not connected.',stage='preview')
            self.previewing = True

    def stop_live_view(self):
        with self.condition:self.previewing = False

    def _unavailable(self):
        code = 'camera_read_failed' if self.last_error == 'frame_read_failed' else 'disconnected'
        raise CameraError(code,'Host webcam frame reader stopped. Check camera access/USB; this is not an HTTP or Wi-Fi error.',stage='preview')

    def get_preview_frame(self):
        with self.condition:
            if not self.connected:self._unavailable()
            if not self.previewing:raise CameraError('preview_stopped','Live View is stopped.',stage='preview')
            if self.preview is None or self.preview.sequence <= self.delivered:
                raise CameraError('preview_pending','Waiting for a new webcam frame; keeping the existing camera connection.',stage='preview')
            self.delivered = self.preview.sequence
            return self.preview

    def capture_photo(self, capture_id, deadline):
        capture_id = str(uuid.UUID(capture_id))
        if not self.capture_lock.acquire(blocking=False):raise CameraError('busy','Webcam capture is already in progress.')
        try:
            path = self.root/'camera_spool'/f'{capture_id}.jpg'
            if time.monotonic() >= deadline:raise CameraError('timeout','Webcam capture deadline exceeded.')
            if path.exists():return capture_id
            with self.condition:
                sequence = self.sequence
                while True:
                    if not self.connected or self.stop.is_set():self._unavailable()
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:raise CameraError('timeout','Webcam did not deliver a new capture frame. Previously saved photos are safe.')
                    if self.latest and self.latest[0] > sequence:
                        frame = self.latest[2]
                        break
                    self.condition.wait(remaining)
            ok,data = self.cv.imencode('.jpg',frame)  # Full native size, OpenCV's original default quality.
            if not ok:raise CameraError('transfer','Could not encode webcam capture.',stage='transfer')
            atomic_write(path,data.tobytes())
            if time.monotonic() > deadline:raise CameraError('timeout','Webcam capture was saved after its deadline.',uncertain=True)
            return capture_id
        finally:self.capture_lock.release()

    def get_captured_photo(self, reference, deadline):
        reference = str(uuid.UUID(reference))
        if time.monotonic() >= deadline:raise CameraError('timeout','Webcam transfer deadline exceeded.',stage='transfer')
        path = self.root/'camera_spool'/f'{reference}.jpg'
        if not path.is_file():raise CameraError('transfer','Webcam DEMO capture is missing from its spool.',stage='transfer')
        return CapturedPhoto(path.read_bytes(),'image/jpeg','webcam_frame')
