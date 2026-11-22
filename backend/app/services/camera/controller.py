"""One host camera, one active session, durable capture journal and safe replay."""
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from dataclasses import replace
from fastapi import HTTPException
from .base import CameraError
from .mock import MockCameraAdapter
from .uvc_demo import UvcDemoCameraAdapter
from .vendor import VendorCameraAdapter
from .sony_zve10 import SonyZvE10CameraAdapter
from .sony_ptp import SonyPtpDriver
from .sony_wia import MAX_TRANSFER as SONY_MAX_TRANSFER
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
        self.transitioning = False
        self.owner = None
        self.release_requested = None
        self.reconciled_session = None
        self.capture_progress = None
        self.capture_progress_request = None
        self.lease_until = 0
        self.state = 'idle'
        self.last_error = None
        self.last_frame_at = None
        self.last_frame_sequence = None
        self.preview_epoch = 0
        self.preview_samples = deque(maxlen=120)
        self.frame_diagnostics = {'requests':0,'busy':0,'failures':0,'last_failure':None,'processing_ms':None}
        self.stop_event = threading.Event()
        self.last_diagnostic = None
        self.process_lock = None
        self.thread = None

    def make_adapter(self, mode):
        if mode == 'mock':return MockCameraAdapter()
        if mode == 'sony_zve10':return SonyZvE10CameraAdapter(storage_root=self.settings.storage_root,timeout=self.settings.camera_timeout_seconds)
        if mode == 'uvc_demo':
            if not (self.settings.demo_hardware_allowed and
                    (self.settings.app_env=='development' or self.settings.operation_mode=='rehearsal')):
                raise CameraError('demo_only','UVC DEMO requires Development or explicitly authorized Rehearsal; it is not a real shutter.',stage='connect')
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
        self._reconcile_cancelled_receipts()
        with self.repo.db.connect() as db:
            db.execute("UPDATE camera_captures SET status='failed',uncertain=1,error_code='interrupted',error_message=?,updated_at=? WHERE status='capturing'",('Host bị ngắt khi đang chụp. Kiểm tra camera trước khi chụp lại.',now()))
            db.execute("UPDATE camera_captures SET status='transfer_failed',error_code='interrupted_transfer',error_message=?,updated_at=? WHERE status='transferring'",('Truyền file bị ngắt. Thử lại cùng key, không chụp thêm.',now()))

    def _reconcile_cancelled_receipts(self):
        # A crash may occur after the archived receipt is committed but before
        # SQLite acknowledges cancellation. Replay only that durable decision;
        # no physical-idle inference and no USB/control commands are involved.
        driver=getattr(self.adapter,'driver',None)
        if not isinstance(driver,SonyPtpDriver):return
        with self.repo.db.connect() as db:
            rows=db.execute("""SELECT c.id FROM camera_captures c JOIN sessions s ON s.id=c.session_id
                WHERE c.adapter_mode='sony_zve10' AND c.status IN ('failed','transfer_failed')
                AND c.native_path IS NULL AND COALESCE(c.error_code,'')!='capture_cancelled'
                AND s.status!='completed'
                AND NOT EXISTS(SELECT 1 FROM session_finals f WHERE f.session_id=s.id)""").fetchall()
            for row in rows:
                journal,_=driver._paths(row['id'])
                archive=driver.root/'cancelled'/journal.name
                if not journal.is_file() or not archive.is_file():continue
                raw=journal.read_bytes()
                record=json.loads(raw)
                if record.get('status')!='cancelled':continue
                uncertain=record.get('physical_outcome')=='uncertain'
                if uncertain and (not record.get('isolation_verified_at') or archive.read_bytes()!=raw):continue
                db.execute("""UPDATE camera_captures SET status='failed',error_code='capture_cancelled',
                    error_message=?,uncertain=?,updated_at=? WHERE id=?""",
                    ('Reconciled durable cancellation receipt; original receipt and photos retained.',int(uncertain),now(),row['id']))

    def _reserve_transition(self, stage='connect'):
        # Caller holds control. Reserve first so new frames cannot overtake a
        # disconnect waiting for an already running frame to leave I/O.
        self._check_work(stage)
        if self.capture_lock.locked():
            raise CameraError('busy','Camera đang chụp/truyền ảnh.',stage=stage)
        self.transitioning = True
        self.preview_epoch += 1
        self.last_frame_at = None

    def _check_work(self, stage):
        if self.stop_event.is_set():
            raise CameraError('disconnected','Host đang dừng camera.',stage=stage)
        if self.transitioning:
            raise CameraError('busy','Camera đang kết nối hoặc đang đóng phiên.',stage=stage)

    @contextmanager
    def _transition_io(self, acquired=False):
        if not acquired:self.io.acquire()
        try:
            if self.stop_event.is_set():
                raise CameraError('disconnected','Host đang dừng camera.',stage='connect')
            yield
        finally:
            self.io.release()
            with self.control:self.transitioning = False

    def _close_camera(self):
        # Adapter.disconnect owns its Live View teardown as well as the device.
        # Keep the lease if cleanup fails: another session cannot take over.
        try:self.adapter.disconnect()
        except Exception as error:
            with self.control:
                if self.last_error != str(error):
                    logging.getLogger(__name__).warning('Camera cleanup failed; ownership retained (%s)',error)
                self.release_requested = self.owner
                self.state = 'error'
                self.last_error = str(error)
            raise
        with self.control:
            self.owner = self.release_requested = None
            self.lease_until = 0
            self.state = 'disconnected'
            self.last_error = self.last_frame_at = None

    def _expire(self):
        with self.control:
            if (self.stop_event.is_set() or self.transitioning or self.capture_lock.locked()
                    or not self.owner or (self.release_requested != self.owner and time.monotonic() <= self.lease_until)):
                return
            if not self.io.acquire(blocking=False):return
            try:self._reserve_transition()
            except CameraError:
                self.io.release()
                return  # A capture may have just acquired its admission lock.
        try:
            with self._transition_io(acquired=True):self._close_camera()
        except Exception:
            pass  # _close_camera reports the failure; the lease monitor retries.

    def _owned(self, sid):
        if self.owner != sid or self.release_requested == sid or time.monotonic() > self.lease_until:
            raise CameraError('not_connected','Phiên chưa giữ camera. Bấm Kết nối lại camera.',stage='connect')
        self.lease_until = time.monotonic()+self.settings.camera_lease_seconds

    def check_event_capabilities(self, adapter=None):
        cap=(adapter or self.adapter).get_capabilities()
        if cap.demo and not self.settings.demo_hardware_allowed:
            raise CameraError('event_hardware_required','Camera thật chưa sẵn sàng. Nhờ Host kiểm tra cấu hình; chế độ Event không cho phép camera mô phỏng.',stage='connect')
        if self.settings.operation_mode=='event' and not (cap.capture and cap.physical_shutter and cap.original_file and cap.hardware_verified):
            raise CameraError('event_hardware_required','Camera/SDK chưa được xác minh chụp JPG gốc trên máy này. Nhờ Host kiểm tra thiết bị.',stage='connect')

    def status(self, sid=None, token=None, *, progress_key=None, check_capture=False):
        if sid:self.authorize(sid,token)
        self._expire()
        with self.control:
            cap = self.adapter.get_capabilities().json()
            status = self.adapter.get_status()
            fresh = bool(status['previewing'] and self.last_frame_at and time.time()-self.last_frame_at <= self.settings.camera_stale_seconds)
            driver=getattr(self.adapter,'driver',None)
            if check_capture and isinstance(driver,SonyPtpDriver):driver.check_capture_abandonment()
            if not status['connected']:capture_readiness='disconnected'
            elif self.capture_lock.locked():capture_readiness='busy'
            elif isinstance(driver,SonyPtpDriver) and driver.unresolved:capture_readiness='reconciliation_required'
            else:capture_readiness='preflight_required'
            progress=self.capture_progress if sid is None or sid==self.owner else None
            driver_progress=getattr(driver,'capture_progress',None)
            if sid and progress_key and progress and self.capture_progress_request==(sid,progress_key,progress['capture_id']):
                stage, timings = progress['stage'], progress['timings_ms']
                fresh_shot=stage=='shutter' or 'shutter' in timings
                native_ack=driver_progress and driver_progress['capture_id']==progress['capture_id'] and driver_progress.get('shutter_acknowledged')
                progress={**progress,
                    'shutter_acknowledged':bool(fresh_shot and (native_ack or stage=='receiving_original' or 'receiving_original' in timings)),
                    'jpeg_validated':stage in ('saving_original','saving_slot','complete') or 'saving_original' in timings,
                    'jpeg_saved':stage=='complete'}
            return {'state':self.state,**status,'capabilities':cap,'guest_enabled':self.enabled(),
                    'busy':self.capture_lock.locked(),'owned_by_session':bool(sid and self.owner==sid),
                    'lease_active':bool(self.owner),'preview_healthy':fresh,'capture_readiness':capture_readiness,
                    'last_frame_at':self.last_frame_at,'last_error':self.last_error,
                    'frame_diagnostics':dict(self.frame_diagnostics),
                    'capture_progress':progress,
                    'camera_progress':driver_progress if sid is None or sid==self.owner else None,
                    'preview_performance':self.preview_performance(),
                    'timeout_seconds':self.settings.camera_timeout_seconds,
                    'stale_seconds':self.settings.camera_stale_seconds,
                    'operation_mode':self.settings.operation_mode,'configured_model':self.settings.camera_model}

    def _capture_stage(self, capture_id, stage):
        stamp=time.monotonic();previous=self.capture_progress
        continuing=stage!='preparing' and previous and previous['capture_id']==capture_id
        timings=dict(previous['timings_ms']) if continuing else {}
        if continuing:
            timings[previous['stage']]=round((stamp-previous['monotonic'])*1000,2)
        self.capture_progress={'capture_id':capture_id,'stage':stage,'at':now(),'monotonic':stamp,'timings_ms':timings}
        logging.getLogger('uvicorn.error').info('camera_capture capture_id=%s stage=%s at=%s timings_ms=%s',capture_id,stage,self.capture_progress['at'],timings)

    @contextmanager
    def _capture_io(self, deadline):
        remaining=deadline-time.monotonic()
        if remaining<=0 or not self.io.acquire(timeout=remaining):
            raise CameraError('busy','Camera I/O is still occupied. No new shutter was sent; retry the same request after the current operation ends.',stage='capture',shutter_dispatched=False)
        try:yield
        finally:self.io.release()

    def diagnose(self, *, confirm_physical_shutter=False):
        """Return safe capability/status diagnostics for the Host UI.

        This intentionally never calls capture_photo or get_captured_photo.
        A real shutter test needs a separate, explicitly confirmed test
        session so a dashboard click cannot trigger an untracked photo.
        """
        self._expire()
        with self.control:
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
        self._expire()
        with self.control:
            self._check_work('connect')
            if not self.enabled():raise CameraError('disabled','Host chưa bật camera guest control.',stage='connect')
            if self.owner and self.owner != sid:raise CameraError('busy','Camera đang phục vụ một phiên khác.',stage='connect')
            if self.capture_lock.locked():raise CameraError('busy','Camera đang chụp/truyền ảnh.',stage='connect')
            if self.release_requested or (self.owner and time.monotonic() > self.lease_until):
                raise CameraError('busy','Phiên camera trước chưa được nhả.',stage='connect')
            self._acquire_process()
            self.check_event_capabilities()
            current = self.adapter.get_status()
            if self.owner == sid and current['connected']:
                self.lease_until = time.monotonic()+self.settings.camera_lease_seconds
                self.state = 'previewing' if current['previewing'] else 'ready'
                return self.status(sid,token)
            self._reserve_transition()
            self.state = 'connecting'
        with self._transition_io():
            try:
                self.adapter.connect()
            except CameraError as error:
                error.stage = 'connect'
                logging.getLogger(__name__).warning('camera_connect_failed adapter=%s code=%s: %s',self.mode,error.code,error)
                with self.control:self.state = 'error';self.last_error = str(error)
                raise
            with self.control:
                self.reconciled_session = None
                self.last_frame_sequence = None
                self.preview_samples.clear()
                self.owner = sid;self.lease_until = time.monotonic()+self.settings.camera_lease_seconds
                self.state = 'ready';self.last_error = None
        return self.status(sid,token)

    def live(self, sid, token, start):
        self.authorize(sid,token)
        with self.control:
            self._check_work('preview')
            self._owned(sid)
            self._reserve_transition('preview')
        with self._transition_io():
            if start:self.adapter.start_live_view()
            else:self.adapter.stop_live_view()
            with self.control:self.state = 'previewing' if start else 'ready'
        return self.status(sid,token)

    def disconnect(self, sid=None, token=None):
        if sid:self.authorize(sid,token)
        with self.control:
            if sid and self.owner not in (None,sid):raise CameraError('busy','Camera thuộc phiên khác.',stage='connect')
            if self.capture_lock.locked():
                # Honor an explicit release after the in-flight request exits;
                # never interrupt WIA or strand the next session until lease expiry.
                self.release_requested=self.owner
                raise CameraError('busy','Đang chụp/truyền ảnh; camera sẽ được nhả khi yêu cầu hiện tại kết thúc.',stage='connect')
            self._reserve_transition()
        with self._transition_io():self._close_camera()
        return {'state':'disconnected'}

    def frame(self, sid, token):
        self.authorize(sid,token)
        waiting=time.perf_counter()
        with self.control:
            self._check_work('preview')
            self._owned(sid)
            self.frame_diagnostics['requests'] += 1
            if self.capture_lock.locked() or not self.io.acquire(blocking=False):
                self.frame_diagnostics['busy'] += 1
                raise CameraError('busy','Đang chụp/truyền ảnh; preview tạm dừng.',stage='preview')
            adapter=self.adapter
            epoch=self.preview_epoch
            lock_ms=(time.perf_counter()-waiting)*1000
        # Serialize camera I/O, but do not hold the controller/status lock while
        # USB waits. A reserved transition invalidates an in-flight frame.
        try:
            started = time.perf_counter()
            try:
                frame = adapter.get_preview_frame()
                with self.control:
                    if self.adapter is not adapter or self.owner!=sid or self.preview_epoch!=epoch or time.monotonic()>self.lease_until:
                        raise CameraError('not_connected','Camera preview belongs to a released session.',stage='preview')
                    if time.time()-frame.captured_at > self.settings.camera_stale_seconds:
                        self.last_frame_at = None
                        raise CameraError('stale_preview','Live View đã cũ/đứng hình. Kết nối lại camera.',stage='preview')
                    if self.last_frame_sequence is not None and frame.sequence<=self.last_frame_sequence:
                        raise CameraError('preview_pending','Waiting for a newer camera frame.',stage='preview')
                    self.last_frame_sequence=frame.sequence
                    self.last_frame_at = frame.captured_at
                    self.frame_diagnostics['last_failure'] = None
                    self.state = 'previewing';self.last_error = None
                    self.preview_samples.append({'at':time.monotonic(),'processing_ms':(time.perf_counter()-started)*1000,
                        'lock_ms':lock_ms,'age_ms':max(0,(time.time()-frame.captured_at)*1000),**(frame.timings or {})})
                    return frame
            except CameraError as error:
                error.stage = 'preview'
                with self.control:
                    if self.adapter is adapter and self.owner==sid and self.preview_epoch==epoch:
                        self.frame_diagnostics['failures'] += 1
                        if self.frame_diagnostics['last_failure']!=error.code or self.last_error!=str(error):
                            logging.getLogger(__name__).warning('camera_preview_failed adapter=%s code=%s: %s',self.mode,error.code,error)
                        self.frame_diagnostics['last_failure'] = error.code
                        self.state = ('waiting' if error.code in ('preview_pending','not_ready','busy') else
                                      'disconnected' if error.code in ('disconnected','transport_failed') else 'error')
                        self.last_error = str(error)
                        if error.code not in ('preview_pending','not_ready','busy'):self.last_frame_at = None
                raise
            finally:
                self.frame_diagnostics['processing_ms'] = round((time.perf_counter()-started)*1000,1)
        finally:self.io.release()

    def preview_performance(self):
        samples=list(self.preview_samples)
        result={'samples':len(samples),'delivered_fps':round((len(samples)-1)/(samples[-1]['at']-samples[0]['at']),2)
            if len(samples)>1 and samples[-1]['at']>samples[0]['at'] else None}
        for name in ('processing_ms','lock_ms','age_ms','driver_lock_ms','properties_ms','object_info_ms','acquisition_ms','wia_worker_ms','wia_ipc_overhead_ms','validation_ms'):
            values=sorted(sample[name] for sample in samples if name in sample)
            if values:result[name]={'p50':round(values[(len(values)-1)//2],2),'p95':round(values[min(len(values)-1,int(len(values)*.95))],2),'max':round(values[-1],2)}
        return result

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

    def _capture_replay(self, row, sid, token, slot):
        if not row:return None
        if row['slot_index'] != slot:raise HTTPException(409,'Idempotency-Key đã dùng cho slot khác')
        if row['status']=='captured':return self.result(sid,token,row['id'])
        if row['error_code'] in ('capture_cancelled','capture_superseded'):
            raise CameraError(row['error_code'],'Yêu cầu chụp cũ đã đóng. Ảnh đã lưu vẫn được giữ; hãy tiếp tục trong phiên hiện tại.',stage='capture')
        if row['status']=='failed' and not (self.mode=='sony_zve10'
                and isinstance(getattr(self.adapter,'driver',None),SonyPtpDriver)):
            raise CameraError(row['error_code'] or 'failed',row['error_message'] or 'Capture thất bại.',uncertain=bool(row['uncertain']))
        return None

    def _supersede_previous_captures(self, sid, deadline):
        # Caller holds capture_lock AND io; no old shutter/transfer can be in
        # flight here. Older tabs cannot supersede a newer session's capture.
        driver=getattr(self.adapter,'driver',None)
        if not isinstance(driver,SonyPtpDriver):return
        driver.require_unassigned_recovery_complete()
        with self.repo.db.connect() as db:
            # A retry of the CURRENT session already owns the camera buffer.
            # Do not let an empty old tombstone consume its pending JPEG.
            current=db.execute("SELECT id,error_code FROM camera_captures WHERE session_id=? AND adapter_mode='sony_zve10' AND status!='captured'",(sid,)).fetchall()
            for row in current:
                journal,_=driver._paths(row['id'])
                # A retired tab must not reopen A with a fresh key after B has
                # finished. The receipt also covers a crash before the DB ACK.
                if row['error_code']=='capture_superseded' or (journal.exists() and
                        json.loads(journal.read_text(encoding='utf-8')).get('superseded_by')):
                    raise CameraError('capture_superseded','Phiên cũ đã nhường camera. Hãy chọn Phiên mới; ảnh và receipt cũ vẫn được giữ, chưa gửi shutter mới.',stage='capture')
            if any(driver._paths(row['id'])[0] in driver.unresolved for row in current):return
            rows=db.execute('''SELECT c.* FROM camera_captures c
                JOIN sessions old ON old.id=c.session_id JOIN sessions current ON current.id=?
                WHERE c.adapter_mode='sony_zve10' AND c.session_id!=?
                AND old.created_at<current.created_at AND c.status!='captured'
                AND COALESCE(c.error_code,'')!='capture_cancelled'
                AND (c.error_code IS NULL OR c.error_code!='capture_superseded' OR c.native_path IS NULL)
                AND old.status!='completed'
                AND NOT EXISTS(SELECT 1 FROM session_finals f WHERE f.session_id=old.id)
                ORDER BY c.created_at DESC''',(sid,sid)).fetchall()
        for row in rows:
            journal,_=driver._paths(row['id'])
            if not journal.exists():continue  # No durable shutter intent to retire.
            preserved=None
            try:
                preserved=driver.supersede_capture(row['id'],row['session_id'],sid,deadline)
            finally:
                # The receipt is the durable write-ahead audit. If the process
                # crashes before this DB update, the next handoff reconciles it.
                record=json.loads(journal.read_text(encoding='utf-8'))
                if record.get('superseded_by') and record.get('status')!='cancelled':
                    with self.repo.db.connect() as db:
                        db.execute("""UPDATE camera_captures SET status='failed',error_code='capture_superseded',
                            error_message=?,uncertain=?,native_path=COALESCE(native_path,?),
                            native_sha256=COALESCE(native_sha256,?),mime=COALESCE(mime,?),updated_at=?
                            WHERE id=? AND status!='captured'""",
                            ('Đã nhường camera cho phiên mới; receipt và JPEG cũ được giữ riêng.',
                             int(record.get('status')!='superseded'),
                             preserved['path'] if preserved else None,preserved['sha256'] if preserved else None,
                             preserved['mime'] if preserved else None,now(),row['id']))
        # Independent diagnostics can leave a receipt without a Host DB row.
        # Reuse exactly the same bounded recovery/identity barrier, rather than
        # leaving such receipts permanently invisible to session handoff.
        if self.reconciled_session!=sid:
            with self.repo.db.connect() as db:
                known={row[0] for row in db.execute('SELECT id FROM camera_captures')}
            driver.reconcile_previous_captures(sid,deadline,exclude=known)
            self.reconciled_session=sid

    def capture(self, sid, token, key, slot, *, recovery_only=False):
        session = self.authorize(sid,token)
        with self.control:
            if self.stop_event.is_set():
                raise CameraError('disconnected','Host đang dừng camera.',shutter_dispatched=False)
            self._acquire_process()
        if not 0 <= slot < session['slot_count']:raise HTTPException(422,'Slot nằm ngoài phiên')
        # Replay saved ACKs before needing device/lease. A lost response must
        # never issue another shutter command, including after a restart.
        with self.repo.db.connect() as db:
            old = db.execute('SELECT * FROM camera_captures WHERE session_id=? AND request_key=?',(sid,key)).fetchone()
        replay=self._capture_replay(old,sid,token,slot)
        if replay is not None:return replay
        if recovery_only and not old:
            raise CameraError('capture_not_found','The Host has no capture to recover for this request. No new shutter command was sent.',stage='transfer',shutter_dispatched=False)
        self.repo.require_working(session)
        # Native camera transfer is not a browser upload. Keep HTTP upload limits
        # unchanged while honoring the Sony transport's bounded original size.
        camera_settings=replace(self.settings,max_upload_bytes=max(self.settings.max_upload_bytes,SONY_MAX_TRANSFER)) if self.mode=='sony_zve10' else self.settings
        reserve=camera_settings.max_upload_bytes+self.settings.max_image_pixels*4 if self.mode=='sony_zve10' else self.settings.max_upload_bytes*2
        self.repo.ensure_disk_space(reserve)
        if not self.capture_lock.acquire(blocking=False):raise CameraError('busy','Một lệnh chụp đang được xử lý. Đọc trạng thái/thử lại cùng key.',shutter_dispatched=False)
        capture_id = old['id'] if old else str(uuid.uuid4())
        shutter_dispatched = False
        try:
            self._capture_stage(capture_id,'preparing')
            # A request may have been descheduled between lookup and lock
            # acquisition while an identical request completed. Read its ACK
            # again before inserting an intent or touching the camera.
            with self.repo.db.connect() as db:
                old=db.execute('SELECT * FROM camera_captures WHERE session_id=? AND request_key=?',(sid,key)).fetchone()
            if old:capture_id=old['id']
            replay=self._capture_replay(old,sid,token,slot)
            if replay is not None:return replay
            self.capture_progress_request=(sid,key,capture_id)
            with self.control:
                # An unused session may have changed layout while this command
                # was waiting for the controller. Check the current slot bound
                # before issuing a shutter or writing the capture journal.
                session = self.authorize(sid,token)
                if not 0 <= slot < session['slot_count']:
                    raise HTTPException(422,'Slot nằm ngoài phiên')
                self._check_work('capture')
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
            self._capture_stage(capture_id,'waiting_io')
            with self._capture_io(deadline):
                self._capture_stage(capture_id,'reconciling')
                self._supersede_previous_captures(sid,deadline)
                self._capture_stage(capture_id,'recovering' if old else 'shutter')
                if not old:
                    self.state = 'capturing'
                    shutter_dispatched = None  # A failed command may have reached the camera.
                    reference = self.adapter.capture_photo(capture_id,deadline)
                    shutter_dispatched = True
                    with self.repo.db.connect() as db:
                        db.execute("UPDATE camera_captures SET adapter_reference=?,status='transferring',updated_at=? WHERE id=?",(reference,now(),capture_id))
                elif old['status']=='failed' and self.mode=='sony_zve10':
                    # The real Sony driver checks its durable intent first:
                    # existing intent -> reconcile ONLY; no intent -> preflight
                    # failed before shutter and the same ID may try once safely.
                    if recovery_only:
                        driver=getattr(self.adapter,'driver',None)
                        if not isinstance(driver,SonyPtpDriver) or not driver._paths(capture_id)[0].is_file():
                            raise CameraError('capture_not_found','The Host has no shutter receipt to recover. No new shutter command was sent.',stage='transfer',uncertain=bool(old['uncertain']),shutter_dispatched=False)
                        reference = self.adapter.recover_capture(capture_id,deadline)
                    else:
                        shutter_dispatched = None
                        reference = self.adapter.capture_photo(capture_id,deadline)
                    with self.repo.db.connect() as db:
                        db.execute("UPDATE camera_captures SET adapter_reference=?,status='transferring',updated_at=? WHERE id=?",(reference,now(),capture_id))
                else:reference = old['adapter_reference']
                self.state = 'transferring'
                self._capture_stage(capture_id,'receiving_original')
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
                self._capture_stage(capture_id,'normalizing')
                # Encode the large Sony working PNG faster, with identical
                # pixels. The original JPEG is persisted separately.
                png_level = 5 if self.mode=='sony_zve10' else 6
                validated = validate_image(data,mime,camera_settings,png_compress_level=png_level)
                cap = self.adapter.get_capabilities()
                if not cap.demo and (source!='camera_original' or mime!='image/jpeg' or not cap.physical_shutter or not cap.original_file):
                    raise CameraError('invalid_provenance','Adapter thật chưa xác nhận shutter/file gốc; từ chối dùng frame thay thế.',stage='transfer')
                relative = f'camera_originals/{sid}/{capture_id}'+{'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp'}[mime]
                self._capture_stage(capture_id,'saving_original')
                atomic_write(self.settings.storage_root/relative,data)
                with self.repo.db.connect() as db:
                    db.execute("UPDATE camera_captures SET native_path=?,native_sha256=?,mime=?,status='transferring',updated_at=? WHERE id=?",(relative,validated.input_hash,mime,now(),capture_id))
                    current = db.execute('SELECT expected_revision FROM camera_captures WHERE id=?',(capture_id,)).fetchone()[0]
                self._capture_stage(capture_id,'saving_slot')
                self.repo.upload_photo(sid,token,'camera_'+capture_id,slot,source,validated,current,capture_id)
                if isinstance(self.adapter,SonyZvE10CameraAdapter):self.adapter.capture_persisted(capture_id)
            self._capture_stage(capture_id,'complete')
            self.state = 'captured';self.last_error = None
            self.lease_until = time.monotonic()+self.settings.camera_lease_seconds
            return self.result(sid,token,capture_id)
        except Exception as error:
            if isinstance(error,CameraError):
                error.capture_id = capture_id
                if error.shutter_dispatched is None:error.shutter_dispatched = shutter_dispatched
                driver=getattr(self.adapter,'driver',None)
                if (error.shutter_dispatched is False and not error.uncertain
                        and (not old or not (old['uncertain'] or old['adapter_reference'] or old['native_path']))
                        and (not isinstance(driver,SonyPtpDriver) or not driver._paths(capture_id)[0].exists())):
                    error.clear_pending=True
            self._capture_stage(capture_id,'blocked_before_shutter' if isinstance(error,CameraError)
                and error.shutter_dispatched is False and error.code in ('camera_recovery_pending','recovery_required')
                and not old else 'error')
            self.last_error = str(error) if isinstance(error,CameraError) else 'Không lưu/nhận được ảnh camera. File cũ vẫn giữ; thử lại cùng key.'
            self.state = 'disconnected' if isinstance(error,CameraError) and error.code in ('disconnect','disconnected','transport_failed') else 'error'
            with self.repo.db.connect() as db:
                record = db.execute('SELECT * FROM camera_captures WHERE id=?',(capture_id,)).fetchone()
                if record and record['status']!='captured' and not (recovery_only and getattr(error,'code',None)=='capture_not_found'):
                    transfer = bool(record['adapter_reference'])
                    uncertain = bool(record['uncertain']) or getattr(error,'uncertain',not transfer)
                    db.execute('UPDATE camera_captures SET status=?,error_code=?,error_message=?,uncertain=?,updated_at=? WHERE id=?',
                               ('transfer_failed' if transfer else 'failed',getattr(error,'code','transfer' if transfer else 'camera_error'),self.last_error,int(uncertain),now(),capture_id))
            raise
        finally:
            self.capture_lock.release()
            self._expire()

    def configure(self, mode=None, guest_enabled=None):
        self._expire()
        with self.control:
            if self.capture_lock.locked() or self.owner:raise CameraError('busy','Ngắt phiên camera đang dùng trước khi đổi cấu hình.',stage='connect')
            self._reserve_transition()
        with self._transition_io():
            if mode:
                adapter=self.make_adapter(mode)
                self.check_event_capabilities(adapter)
                self._close_camera()
                with self.control:
                    self.adapter = adapter;self.mode = mode;self.state = 'idle'
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
                self._expire()
        self.thread = threading.Thread(target=monitor,daemon=True,name='photobooth-camera-lease')
        self.thread.start()

    def stop(self):
        with self.control:
            self.stop_event.set()
            self.preview_epoch += 1
        if self.thread:self.thread.join(2)
        # No new work can reach the device after stop_event. Let an admitted
        # capture finish before releasing the process lease.
        self.capture_lock.acquire(blocking=True)
        try:
            with self.io:
                self._close_camera()
                if self.process_lock:self.process_lock.close();self.process_lock = None
        finally:self.capture_lock.release()
