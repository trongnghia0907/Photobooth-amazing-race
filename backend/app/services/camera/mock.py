import hashlib
from io import BytesIO
import time
from PIL import Image, ImageDraw
from .base import CameraCapabilities, CameraError, CapturedPhoto, PreviewFrame


class MockCameraAdapter:
    def __init__(self):
        self.connected = self.previewing = False
        self.sequence = self.shutter_calls = 0
        self.failure = None

    def get_capabilities(self):
        return CameraCapabilities('mock','Host Mock Camera — DEMO',True,True,True,False,False,'synthetic_file')

    def get_status(self):
        return {'connected':self.connected,'previewing':self.previewing}

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = self.previewing = False

    def start_live_view(self):
        if not self.connected:
            raise CameraError('disconnected','Camera chưa kết nối.',stage='preview')
        self.previewing = True

    def stop_live_view(self):
        self.previewing = False

    def _fail(self, stage):
        if self.failure == stage:
            self.failure = None
            if stage == 'disconnect':self.disconnect()
            raise CameraError(stage,{
                'timeout':'Camera hết thời gian chờ; ảnh cũ vẫn được giữ.',
                'capture':'Mock mô phỏng lỗi chụp; chưa nhận ảnh mới.',
                'transfer':'Mock mô phỏng lỗi truyền file. Thử lại cùng yêu cầu, không chụp lần nữa.',
                'disconnect':'Camera ngắt kết nối trong lúc chụp. Kết nối lại để tiếp tục.',
            }[stage],stage='transfer' if stage == 'transfer' else 'capture')

    def get_preview_frame(self):
        if not self.connected or not self.previewing:
            raise CameraError('disconnected','Live View chưa bật hoặc đã ngắt.',stage='preview')
        self.sequence += 1
        img = Image.new('RGB',(640,480),(25,60,140))
        draw = ImageDraw.Draw(img)
        x = 100 + (self.sequence*7)%400
        draw.ellipse((x,120,x+90,210),fill='#38bdf8')
        draw.text((24,24),'HOST MOCK LIVE VIEW - DEMO',fill='white')
        draw.text((24,440),f'Frame {self.sequence}',fill='white')
        output = BytesIO();img.save(output,'JPEG')
        stamp = time.time()
        if self.failure == 'stale_preview':
            stamp -= 60  # persistent until explicit host fault clear/reconnect
        return PreviewFrame(output.getvalue(),self.sequence,stamp)

    def capture_photo(self, capture_id, deadline):
        if not self.connected:
            raise CameraError('disconnected','Camera chưa kết nối.')
        self.shutter_calls += 1
        for stage in ('timeout','capture','disconnect'):self._fail(stage)
        if time.monotonic() > deadline:
            raise CameraError('timeout','Hết thời gian chụp.')
        return capture_id

    def get_captured_photo(self, reference, deadline):
        self._fail('transfer')
        if time.monotonic() > deadline:
            raise CameraError('timeout','Hết thời gian truyền file.',stage='transfer')
        # Deterministic file generation from a backend-generated capture UUID;
        # not a preview frame or anything supplied by the browser.
        color = tuple(50+b%150 for b in hashlib.sha256(reference.encode()).digest()[:3])
        image = Image.new('RGB',(1600,1200),color)
        draw = ImageDraw.Draw(image)
        draw.text((60,60),'AMAZING RACE 2026 DEMO - NOT A REAL CAMERA',fill='white')
        draw.text((60,100),reference,fill='white')
        buffer = BytesIO();image.save(buffer,'JPEG',quality=94)
        return CapturedPhoto(buffer.getvalue(),'image/jpeg','demo')
