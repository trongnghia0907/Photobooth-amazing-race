"""Optional host webcam DEMO. VideoCapture.read is explicitly a video frame,
never a DSLR physical shutter or original camera JPEG. No cv2 import until connect.
"""
import os
import time
import uuid
from .base import CameraCapabilities, CameraError, CapturedPhoto, PreviewFrame
from ..images import atomic_write


class UvcDemoCameraAdapter:
    def __init__(self, root, index=0):
        self.root, self.index = root, index
        self.device = None
        self.previewing = False
        self.sequence = 0

    def get_capabilities(self):
        return CameraCapabilities('uvc_demo','Host UVC/webcam video-frame — DEMO',True,True,True,False,False,'webcam_frame')

    def get_status(self):
        return {'connected':bool(self.device and self.device.isOpened()),'previewing':self.previewing}

    def connect(self):
        if self.get_status()['connected']:return
        try:
            import cv2
        except ImportError:
            raise CameraError('dependency_missing','UVC DEMO cần opencv-python (requirements-camera-optional.txt). Chưa mở camera.',stage='connect') from None
        self.cv = cv2
        self.device = cv2.VideoCapture(self.index,cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
        if not self.device.isOpened():
            self.disconnect()
            raise CameraError('disconnected','Không mở được webcam host. Kiểm tra device index/quyền Windows và ứng dụng đang giữ camera.',stage='connect')

    def disconnect(self):
        if self.device:self.device.release()
        self.device = None;self.previewing = False

    def start_live_view(self):
        if not self.get_status()['connected']:
            raise CameraError('disconnected','Webcam host chưa kết nối.',stage='preview')
        self.previewing = True

    def stop_live_view(self):self.previewing = False

    def _jpeg(self):
        if not self.get_status()['connected']:
            raise CameraError('disconnected','Webcam host ngắt kết nối.')
        ok,frame = self.device.read()
        if not ok:
            self.disconnect()
            raise CameraError('disconnected','Không nhận được frame từ webcam host.')
        ok,data = self.cv.imencode('.jpg',frame)
        if not ok:raise CameraError('transfer','Không mã hóa được frame webcam.',stage='transfer')
        return data.tobytes()

    def get_preview_frame(self):
        if not self.previewing:raise CameraError('preview_stopped','Live View đã dừng.',stage='preview')
        data = self._jpeg();self.sequence += 1
        return PreviewFrame(data,self.sequence,time.time())

    def capture_photo(self, capture_id, deadline):
        uuid.UUID(capture_id)
        if time.monotonic()>deadline:raise CameraError('timeout','Webcam hết thời gian chờ.')
        path = self.root/'camera_spool'/f'{capture_id}.jpg'
        if not path.exists():atomic_write(path,self._jpeg())
        if time.monotonic()>deadline:raise CameraError('timeout','Webcam driver chậm; kiểm tra host.',uncertain=True)
        return capture_id

    def get_captured_photo(self, reference, deadline):
        uuid.UUID(reference)
        path = self.root/'camera_spool'/f'{reference}.jpg'
        if not path.is_file():raise CameraError('transfer','File webcam DEMO không còn trong spool.',stage='transfer')
        return CapturedPhoto(path.read_bytes(),'image/jpeg','webcam_frame')
