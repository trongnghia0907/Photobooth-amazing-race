"""One host camera, one active session, durable capture journal and safe replay."""
import hashlib
import json
import os
import threading
import time
import uuid
from fastapi import HTTPException
from .base import CameraError
from .mock import MockCameraAdapter
from .uvc_demo import UvcDemoCameraAdapter
from .vendor import VendorCameraAdapter
from .sony_zve10 import SonyZvE10CameraAdapter
from ..images import atomic_write, validate_image
from ..repository import now


class CameraController:
    def __init__(self, repository, adapter=None):
        self.repo, self.settings = repository, repository.settings
        self.mode = self.settings.camera_adapter
        self.adapter = adapter or self.make_adapter(self.mode)
        self.control = threading.RLock()
        self.capture_lock = threading.Lock()
        self.io = threading.Lock()
        self.owner = None
        self.lease_until = 0
        self.state = 'idle'
        self.last_error = None
        self.last_frame_at = None
        self.stop_event = threading.Event()
        self.last_diagnostic = None
        self.process_lock = None
        self.thread = None

    def make_adapter(self, mode):
        if mode == 'mock':return MockCameraAdapter()
        if mode == 'sony_zve10':return SonyZvE10CameraAdapter()
        if mode == 'uvc_demo':
            if self.settings.app_env != 'development':
                raise CameraError('demo_only','UVC frame fallback chỉ cho development, không phải shutter thật.',stage='connect')
            return UvcDemoCameraAdapter(self.settings.storage_root,self.settings.camera_device_index)
        return VendorCameraAdapter()

    def authorize(self, sid, token):
        with self.repo.db.connect() as db:
            return self.repo.authorize(db,sid,token)

    def enabled(self):
        with self.repo.db.connect() as db:
            row = db.execute("SELECT value FROM host_settings WHERE key='camera_guest_enabled'").fetchone()
        return row['value']=='true' if row else self.settings.camera_guest_enabled

    def _acquire_process(self):
        if self.process_lock:return
        lock = open(self.settings.storage_root/'.camera-controller.lock','a+b')
        try:
            lock.seek(0)
            if os.name == 'nt':
                import msvcrt
                if not lock.read(1):lock.write(b'0');lock.flush()
                lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            lock.close()
            raise CameraError('host_busy','Camera controller thuộc process khác. Chạy Uvicorn với một worker.',stage='connect') from None
        self.process_lock = lock
        with self.repo.db.connect() as db:
            db.execute("UPDATE camera_captures SET status='failed',uncertain=1,error_code='interrupted',error_message=?,updated_at=? WHERE status='capturing'",('Host bị ngắt khi đang chụp. Kiểm tra camera trước khi chụp lại.',now()))
            db.execute("UPDATE camera_captures SET status='transfer_failed',error_code='interrupted_transfer',error_message=?,updated_at=? WHERE status='transferring'",('Truyền file bị ngắt. Thử lại cùng key, không chụp thêm.',now()))

    def _expire(self):
        if self.owner and time.monotonic() > self.lease_until and not self.capture_lock.locked():
            self.adapter.stop_live_view();self.adapter.disconnect()
            self.owner = None;self.state = 'disconnected';self.last_frame_at = None

    def _owned(self, sid):
        self._expire()
        if self.owner != sid:
            raise CameraError('not_connected','Phiên chưa giữ camera. Bấm Kết nối lại camera.',stage='connect')
        self.lease_until = time.monotonic()+self.settings.camera_lease_seconds

    def check_event_capabilities(self, adapter=None):
        cap=(adapter or self.adapter).get_capabilities()
        if cap.demo and not self.settings.demo_hardware_allowed:
            raise CameraError('event_hardware_required','Camera thật chưa sẵn sàng. Nhờ Host kiểm tra cấu hình; chế độ Event không cho phép camera mô phỏng.',stage='connect')
        if self.settings.operation_mode=='event' and not (cap.capture and cap.physical_shutter and cap.original_file and cap.hardware_verified):
            raise CameraError('event_hardware_required','Camera/SDK chưa được xác minh chụp JPG gốc trên máy này. Nhờ Host kiểm tra thiết bị.',stage='connect')

    def status(self, sid=None, token=None):
        if sid:self.authorize(sid,token)
        with self.control:
            self._expire()
            cap = self.adapter.get_capabilities().json()
            status = self.adapter.get_status()
            fresh = bool(status['previewing'] and self.last_frame_at and time.time()-self.last_frame_at <= self.settings.camera_stale_seconds)
            return {'state':self.state,**status,'capabilities':cap,'guest_enabled':self.enabled(),
                    'busy':self.capture_lock.locked(),'owned_by_session':bool(sid and self.owner==sid),
                    'lease_active':bool(self.owner),'preview_healthy':fresh,
                    'last_frame_at':self.last_frame_at,'last_error':self.last_error,
                    'timeout_seconds':self.settings.camera_timeout_seconds,
                    'stale_seconds':self.settings.camera_stale_seconds,
                    'operation_mode':self.settings.operation_mode,'configured_model':self.settings.camera_model}

    def diagnose(self, *, confirm_physical_shutter=False):
        """Return safe capability/status diagnostics for the Host UI.

        This intentionally never calls capture_photo or get_captured_photo.
        A real shutter test needs a separate, explicitly confirmed test
        session so a dashboard click cannot trigger an untracked photo.
        """
        with self.control:
            self._expire()
            capabilities = self.adapter.get_capabilities()
            adapter_status = self.adapter.get_status()
            checked_at = now()
            connected = bool(adapter_status.get('connected'))
            live_supported = bool(capabilities.live_view)
            preview_checked = bool(connected and adapter_status.get('previewing') and self.last_frame_at is not None)
            preview_fresh = bool(preview_checked and time.time()-self.last_frame_at <= self.settings.camera_stale_seconds)
            preview_result = ('UNSUPPORTED' if not live_supported else
                              'NOT_TESTED' if not preview_checked else 'PASS' if preview_fresh else 'FAIL')
            checks = [
                {'name': 'connection', 'status': 'PASS' if connected else 'FAIL',
                 'detail': 'Camera adapter đang kết nối.' if connected else 'Chưa kết nối camera host.',
                 'suggestion': None if connected else 'Kiểm tra kết nối USB, PC Remote và driver của adapter đã chọn.'},
                {'name': 'live_preview', 'status': preview_result,
                 'detail': ('Adapter không hỗ trợ Live Preview.' if not live_supported else
                            'Đã nhận frame Live Preview còn mới.' if preview_fresh else
                            'Frame Live Preview đã cũ; chưa xác nhận camera bị ngắt kết nối.' if preview_checked else
                            'Chưa nhận frame từ Live Preview đang hoạt động; capability không phải kết quả kiểm thử.'),
                 'suggestion': (None if preview_fresh else
                                'Kiểm tra driver/SDK hỗ trợ Live Preview.' if not live_supported else
                                'Mở preview ở Booth, kiểm tra kết nối laptop rồi làm mới chẩn đoán.')},
                {'name': 'physical_shutter', 'status': 'UNSUPPORTED' if not capabilities.physical_shutter else 'NOT_TESTED',
                 'detail': ('Adapter không khai báo shutter vật lý.' if not capabilities.physical_shutter else
                            'Có capability shutter; chưa phát lệnh shutter trong chẩn đoán an toàn.'),
                 'suggestion': ('Không dùng DEMO/webcam để kết luận shutter thật.' if not capabilities.physical_shutter else
                                'Tạo phiên test riêng và xác nhận trước khi chụp thử có chủ đích.')},
                {'name': 'original_file', 'status': 'UNSUPPORTED' if not capabilities.original_file else 'NOT_TESTED',
                 'detail': ('Adapter không khai báo nhận file gốc từ camera.' if not capabilities.original_file else
                            'Có capability file gốc; chưa chụp/nhận file trong chẩn đoán an toàn.'),
                 'suggestion': ('Cấu hình SDK camera thật; không dùng frame preview thay file gốc.' if not capabilities.original_file else
                                'Kiểm thử trong phiên test riêng sau khi xác nhận shutter.')},
            ]
            result = {'adapter': capabilities.json(), 'connection': adapter_status,
                      'state': self.state, 'last_checked_at': checked_at, 'checks': checks,
                      'physical_test': {'requested': bool(confirm_physical_shutter),
                                        'status': 'NOT_TESTED',
                                        'detail': 'Không có lệnh shutter nào được phát từ dashboard; cần phiên test riêng có xác nhận rõ ràng.'}}
            self.last_diagnostic = result
            return result

    def connect(self, sid, token):
        self.repo.require_working(self.authorize(sid,token))
        with self.control:
            self._acquire_process();self._expire()
            if not self.enabled():raise CameraError('disabled','Host chưa bật camera guest control.',stage='connect')
            if self.owner and self.owner != sid:raise CameraError('busy','Camera đang phục vụ một phiên khác.',stage='connect')
            if self.capture_lock.locked():raise CameraError('busy','Camera đang chụp/truyền ảnh.',stage='connect')
            self.state = 'connecting'
            try:
                self.check_event_capabilities()
                self.adapter.connect()
                self.owner = sid;self.lease_until = time.monotonic()+self.settings.camera_lease_seconds
                self.state = 'ready';self.last_error = None
            except CameraError as error:
                self.state = 'error';self.last_error = str(error);raise
        return self.status(sid,token)

    def live(self, sid, token, start):
        self.authorize(sid,token)
        with self.control:
            self._owned(sid)
            if self.capture_lock.locked():raise CameraError('busy','Camera đang chụp/truyền ảnh.',stage='preview')
            if start:self.adapter.start_live_view();self.state = 'previewing'
            else:self.adapter.stop_live_view();self.state = 'ready';self.last_frame_at = None
        return self.status(sid,token)

    def disconnect(self, sid=None, token=None):
        if sid:self.authorize(sid,token)
        with self.control:
            if sid and self.owner not in (None,sid):raise CameraError('busy','Camera thuộc phiên khác.',stage='connect')
            if self.capture_lock.locked():raise CameraError('busy','Đợi chụp/truyền ảnh kết thúc trước khi ngắt.',stage='connect')
            self.adapter.stop_live_view();self.adapter.disconnect()
            self.owner = None;self.last_frame_at = None;self.state = 'disconnected'
        return {'state':'disconnected'}

    def frame(self, sid, token):
        self.authorize(sid,token)
        with self.control:
            self._owned(sid)
            if not self.io.acquire(blocking=False):raise CameraError('busy','Đang chụp/truyền ảnh; preview tạm dừng.',stage='preview')
            try:
                frame = self.adapter.get_preview_frame()
                if time.time()-frame.captured_at > self.settings.camera_stale_seconds:
                    self.last_frame_at = None
                    raise CameraError('stale_preview','Live View đã cũ/đứng hình. Kết nối lại camera.',stage='preview')
                self.last_frame_at = frame.captured_at
                self.state = 'previewing';self.last_error = None
                return frame
            except CameraError as error:
                self.state = 'error';self.last_error = str(error);self.last_frame_at = None;raise
            finally:self.io.release()

    @staticmethod
    def capture_metadata(row):
        return {k:row[k] for k in ('id','session_id','slot_index','adapter_mode','status','photo_id','native_sha256','mime','error_code','error_message','uncertain','created_at','updated_at')}

    def result(self, sid, token, capture_id):
        self.authorize(sid,token)
        with self.repo.db.connect() as db:
            row = db.execute('SELECT * FROM camera_captures WHERE id=? AND session_id=?',(capture_id,sid)).fetchone()
            if not row:raise HTTPException(404,'Không tìm thấy capture')
            snapshot = None
            if row['status']=='captured':
                ack = db.execute('SELECT result_json FROM operations WHERE session_id=? AND operation_key=?',(sid,'camera_'+row['id'])).fetchone()
                if ack:snapshot = json.loads(ack['result_json'])
            return {'capture':self.capture_metadata(row),'session':snapshot}

    def capture(self, sid, token, key, slot):
        session = self.authorize(sid,token)
        with self.control:self._acquire_process()
        if not 0 <= slot < session['slot_count']:raise HTTPException(422,'Slot nằm ngoài phiên')
        # Replay saved ACKs before needing device/lease. A lost response must
        # never issue another shutter command, including after a restart.
        with self.repo.db.connect() as db:
            old = db.execute('SELECT * FROM camera_captures WHERE session_id=? AND request_key=?',(sid,key)).fetchone()
        if old:
            if old['slot_index'] != slot:raise HTTPException(409,'Idempotency-Key đã dùng cho slot khác')
            if old['status']=='captured':return self.result(sid,token,old['id'])
            if old['status']=='failed':raise CameraError(old['error_code'] or 'failed',old['error_message'] or 'Capture thất bại.',uncertain=bool(old['uncertain']))
        self.repo.require_working(session)
        self.repo.ensure_disk_space(self.settings.max_upload_bytes*2)
        if not self.capture_lock.acquire(blocking=False):raise CameraError('busy','Một lệnh chụp đang được xử lý. Đọc trạng thái/thử lại cùng key.')
        capture_id = old['id'] if old else str(uuid.uuid4())
        try:
            with self.control:
                # An unused session may have changed layout while this command
                # was waiting for the controller. Check the current slot bound
                # before issuing a shutter or writing the capture journal.
                session = self.authorize(sid,token)
                if not 0 <= slot < session['slot_count']:
                    raise HTTPException(422,'Slot nằm ngoài phiên')
                self._owned(sid)
                if not self.enabled():raise CameraError('disabled','Host đã tắt điều khiển camera.')
                capabilities = self.adapter.get_capabilities()
                self.check_event_capabilities()
                if not capabilities.capture:raise CameraError('unsupported','Adapter không hỗ trợ chụp; không lấy screenshot thay thế.')
                if not capabilities.demo and (not capabilities.physical_shutter or not capabilities.original_file):
                    raise CameraError('unsupported','Adapter thật chưa hỗ trợ shutter/file gốc. Không gửi lệnh chụp.')
                if old and old['adapter_mode'] != self.mode:raise CameraError('adapter_changed','Adapter đã đổi; Host cần khôi phục adapter cũ để nhận file.',stage='transfer')
            if not old:
                stamp = now()
                with self.repo.db.connect() as db:
                    db.execute('INSERT INTO camera_captures (id,session_id,request_key,slot_index,expected_revision,adapter_mode,status,created_at,updated_at) VALUES (?,?,?,?,?,?,\'capturing\',?,?)',
                               (capture_id,sid,key,slot,session['shots_revision'],self.mode,stamp,stamp))
            deadline = time.monotonic()+self.settings.camera_timeout_seconds
            with self.io:
                if not old:
                    self.state = 'capturing'
                    reference = self.adapter.capture_photo(capture_id,deadline)
                    with self.repo.db.connect() as db:
                        db.execute("UPDATE camera_captures SET adapter_reference=?,status='transferring',updated_at=? WHERE id=?",(reference,now(),capture_id))
                else:reference = old['adapter_reference']
                self.state = 'transferring'
                if old and old['native_path']:
                    root = self.settings.storage_root.resolve();path = (root/old['native_path']).resolve()
                    if not path.is_relative_to(root) or not path.is_file():raise CameraError('transfer','File gốc camera bị mất.',stage='transfer')
                    data,mime = path.read_bytes(),old['mime']
                    if hashlib.sha256(data).hexdigest() != old['native_sha256']:raise CameraError('transfer','File gốc camera đã thay đổi.',stage='transfer')
                    source = 'demo' if self.adapter.get_capabilities().demo and self.mode=='mock' else 'webcam_frame' if self.adapter.get_capabilities().demo else 'camera_original'
                else:
                    photo = self.adapter.get_captured_photo(reference,deadline)
                    data,mime,source = photo.data,photo.mime,photo.source
                if time.monotonic()>deadline:raise CameraError('timeout','Hết thời gian truyền ảnh. Thử lại cùng yêu cầu.',stage='transfer')
                validated = validate_image(data,mime,self.settings)
                cap = self.adapter.get_capabilities()
                if not cap.demo and (source!='camera_original' or mime!='image/jpeg' or not cap.physical_shutter or not cap.original_file):
                    raise CameraError('invalid_provenance','Adapter thật chưa xác nhận shutter/file gốc; từ chối dùng frame thay thế.',stage='transfer')
                relative = f'camera_originals/{sid}/{capture_id}'+{'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp'}[mime]
                atomic_write(self.settings.storage_root/relative,data)
                with self.repo.db.connect() as db:
                    db.execute("UPDATE camera_captures SET native_path=?,native_sha256=?,mime=?,status='transferring',updated_at=? WHERE id=?",(relative,hashlib.sha256(data).hexdigest(),mime,now(),capture_id))
                    current = db.execute('SELECT expected_revision FROM camera_captures WHERE id=?',(capture_id,)).fetchone()[0]
                self.repo.upload_photo(sid,token,'camera_'+capture_id,slot,source,validated,current,capture_id)
            self.state = 'captured';self.last_error = None
            self.lease_until = time.monotonic()+self.settings.camera_lease_seconds
            return self.result(sid,token,capture_id)
        except Exception as error:
            if isinstance(error,CameraError):error.capture_id = capture_id
            self.last_error = str(error) if isinstance(error,CameraError) else 'Không lưu/nhận được ảnh camera. File cũ vẫn giữ; thử lại cùng key.'
            self.state = 'disconnected' if isinstance(error,CameraError) and error.code=='disconnect' else 'error'
            with self.repo.db.connect() as db:
                record = db.execute('SELECT * FROM camera_captures WHERE id=?',(capture_id,)).fetchone()
                if record and record['status']!='captured':
                    transfer = bool(record['adapter_reference'])
                    db.execute('UPDATE camera_captures SET status=?,error_code=?,error_message=?,uncertain=?,updated_at=? WHERE id=?',
                               ('transfer_failed' if transfer else 'failed',getattr(error,'code','transfer' if transfer else 'camera_error'),self.last_error,int(getattr(error,'uncertain',not transfer)),now(),capture_id))
            raise
        finally:self.capture_lock.release()

    def configure(self, mode=None, guest_enabled=None):
        with self.control:
            self._expire()
            if self.capture_lock.locked() or self.owner:raise CameraError('busy','Ngắt phiên camera đang dùng trước khi đổi cấu hình.',stage='connect')
            if mode:
                adapter=self.make_adapter(mode)
                self.check_event_capabilities(adapter)
                self.adapter.disconnect();self.adapter = adapter;self.mode = mode;self.state = 'idle';self.last_error = None
            if guest_enabled is not None:
                with self.repo.db.connect() as db:
                    db.execute("INSERT INTO host_settings VALUES ('camera_guest_enabled',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('true' if guest_enabled else 'false',))
        return self.status()

    def fault(self, failure):
        if not (self.settings.app_env=='development' and self.settings.camera_allow_faults and isinstance(self.adapter,MockCameraAdapter)):
            raise HTTPException(403,'Failure simulation chỉ bật cho Mock development có CAMERA_ALLOW_FAULTS=true')
        if self.capture_lock.locked():raise CameraError('busy','Camera đang chụp.')
        self.adapter.failure = failure

    def start(self):
        def monitor():
            while not self.stop_event.wait(.5):
                with self.control:self._expire()
        self.thread = threading.Thread(target=monitor,daemon=True,name='photobooth-camera-lease')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(2)
        if not self.capture_lock.locked():
            self.disconnect()
            if self.process_lock:self.process_lock.close();self.process_lock = None
