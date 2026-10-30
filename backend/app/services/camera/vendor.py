from .base import CameraCapabilities, CameraError


class VendorCameraAdapter:
    """Deliberately blocked until model, official SDK and device are confirmed."""
    def get_capabilities(self):
        return CameraCapabilities('vendor','Vendor SDK — BLOCKED BY HARDWARE',False,False,False,False,False,'unsupported')

    def get_status(self):
        return {'connected':False,'previewing':False,'blocked_by_hardware':True}

    def connect(self):
        raise CameraError('unsupported','Chưa chốt model máy ảnh/SDK. Không hỗ trợ shutter thật; không thay bằng ảnh preview.',stage='connect')

    def disconnect(self):pass
    def stop_live_view(self):pass
    def start_live_view(self):return self.connect()
    def get_preview_frame(self):return self.connect()
    def capture_photo(self, capture_id, deadline):return self.connect()
    def get_captured_photo(self, reference, deadline):return self.connect()
