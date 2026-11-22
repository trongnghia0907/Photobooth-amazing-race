"""Original ZV-E10 control using the documented Camera Control PTP 2 profile.

References: Sony CRC 2.02.00, PTP 2 reference pp. 15-22, 27-38, 61, 70,
87-88 and 98-99; Microsoft WIA vendor-extended-commands. No vendor source or
reference assets are distributed. Polling Shooting File Info is Sony's documented
alternative to ObjectAdded events. This is real protocol code, NOT evidence of
physical hardware verification.
"""
from io import BytesIO
import hashlib
import json
import logging
from pathlib import Path
import shutil
import struct
import threading
import time
import uuid
from datetime import datetime, timezone
from PIL import Image, UnidentifiedImageError
from .base import CameraCapabilities, CameraError, CapturedPhoto, PreviewFrame
from .sony_wia import MAX_TRANSFER, WindowsWiaTransport
from ..images import atomic_write, is_jpeg_image

SHOT = 0xffffc001
LIVE = 0xffffc002
FILE_INFO = 0xd215
LIVE_STATUS = 0xd221
SAVE_DESTINATION = 0xd222
ONE_SHOT = 0xd2c7
SHUTTER_RELEASE = 0xd2c2
HALF_RELEASE = 0xd2c1
FOCUS_MODE = 0x500a
FOCUS_FOUND = 0xd213


class Reader:
    def __init__(self, data):
        self.data, self.offset = data, 0

    def take(self, size):
        if not 0 <= size <= len(self.data) - self.offset:
            raise CameraError('protocol', 'Truncated or invalid Sony PTP dataset.')
        result = self.data[self.offset:self.offset+size]
        self.offset += size
        return result

    def number(self, size, signed=False):
        return int.from_bytes(self.take(size), 'little', signed=signed)

    def string(self):
        count = self.number(1)
        if not count:return ''
        raw = self.take(count * 2)
        if raw[-2:] != b'\0\0':
            raise CameraError('protocol', 'Invalid PTP string terminator.')
        try:return raw[:-2].decode('utf-16-le')
        except UnicodeError:
            raise CameraError('protocol', 'Invalid PTP string encoding.') from None

    def array(self, width=2):
        count = self.number(4)
        if count > 4096:
            raise CameraError('protocol', 'Sony PTP array exceeds limit.')
        return [self.number(width) for _ in range(count)]

    def value(self, datatype):
        if datatype == 0xffff:return self.string()
        scalar = datatype & ~0x4000
        if scalar not in range(1, 11):
            raise CameraError('protocol', 'Unsupported Sony PTP property datatype.')
        width = 1 << ((scalar - 1)//2)
        if datatype & 0x4000:
            count = self.number(4)
            if count > 4096:raise CameraError('protocol', 'Sony property array exceeds limit.')
            return [self.number(width, scalar % 2 == 1) for _ in range(count)]
        return self.number(width, scalar % 2 == 1)


def device_info(data):
    reader = Reader(data)
    reader.take(8)  # StandardVersion, VendorExtensionID, VendorExtensionVersion
    reader.string()
    reader.take(2)  # FunctionalMode
    operations, events, properties, capture_formats, image_formats = [reader.array() for _ in range(5)]
    manufacturer, model, version = [reader.string() for _ in range(3)]
    reader.string()  # Serial number is deliberately not retained or exposed.
    return {'manufacturer':manufacturer, 'model':model, 'firmware':version,
            'operations':operations}


def property_info(data):
    # The PTP 2 Windows example uses one enum list; the current reference also
    # specifies a second Get/Set list. Accept either complete, bounded dataset,
    # never heuristic scanning for property bytes inside an unknown value.
    for lists in (2, 1):
        try:
            reader = Reader(data)
            count = reader.number(8)
            if count > 1024:raise CameraError('protocol', 'Too many Sony properties.')
            result = {}
            for _ in range(count):
                code, datatype = reader.number(2), reader.number(2)
                get_set, enabled = reader.number(1), reader.number(1)
                reader.value(datatype)
                value = reader.value(datatype)
                flag = reader.number(1)
                if flag == 1:
                    for _ in range(3):reader.value(datatype)
                elif flag == 2:
                    for _ in range(lists):
                        entries = reader.number(2)
                        if entries > 4096:raise CameraError('protocol', 'Too many enum values.')
                        for _ in range(entries):reader.value(datatype)
                elif flag != 0:
                    raise CameraError('protocol', 'Unknown Sony property form.')
                if code in result:raise CameraError('protocol', 'Duplicate Sony property.')
                result[code] = {'value':value, 'enabled':enabled, 'settable':get_set == 1}
            if reader.offset != len(data):raise CameraError('protocol', 'Unexpected Sony property bytes.')
            return result
        except CameraError:
            continue
    raise CameraError('protocol', 'Invalid Sony property dataset; no camera settings were changed.')


def object_info(data):
    reader = Reader(data)
    reader.take(4)
    fmt = reader.number(2)
    reader.take(2)
    size = reader.number(4)
    reader.take(14)  # Thumbnail format, size, width, height
    width, height = reader.number(4), reader.number(4)
    reader.take(14)  # Bit depth, parent, association type/description
    sequence = reader.number(4)
    name = reader.string()
    if not 0 < size <= MAX_TRANSFER:
        raise CameraError('transfer', 'Sony object size is invalid or exceeds 64 MiB.', stage='transfer')
    return {'format':fmt, 'size':size, 'width':width, 'height':height,
            'sequence':sequence, 'name':name}


def check_jpeg(data, *, preview=False):
    try:
        with Image.open(BytesIO(data)) as image:
            if not is_jpeg_image(image):raise ValueError()
            image.seek(0)
            if image.width * image.height > (8_000_000 if preview else 64_000_000):raise ValueError()
            image.load()
            return image.size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise CameraError('preview' if preview else 'transfer', 'Sony returned an invalid JPEG; existing photos are preserved.',
                          stage='preview' if preview else 'transfer') from None


class ValidatedSonyOriginal(CapturedPhoto):
    """Original bytes already fully decoded and checked by SonyPtpDriver."""


class SonyPtpDriver:
    def __init__(self, storage_root, timeout=15, transport=None):
        self.root = Path(storage_root) / 'camera_originals' / 'sony-recovery' if storage_root else None
        self.timeout = timeout
        self.transport = transport or WindowsWiaTransport()
        self.lock = threading.RLock()
        self.connected = self.previewing = False
        self.model = None
        self.sequence = self.preview_limit = 0
        self.next_preview = 0
        self.preview_status_until = 0
        self.properties = {}
        self.unresolved = set()
        self.transfer_cache = {}  # At most one unresolved original, bounded to 64 MiB.
        self.transfer_hashes = {}  # Byte identity retained even if the receipt fsync fails.
        self.fresh_captures = set()  # Acquisition context exists only on this live connection.
        self.capture_progress = None

    def _capture_stage(self, capture_id, stage, *, jpeg_bytes=None, log=True):
        stamp=time.monotonic();previous=self.capture_progress
        same_capture=previous and previous['capture_id']==capture_id
        elapsed=round((stamp-previous['monotonic'])*1000,2) if same_capture else None
        self.capture_progress={'capture_id':capture_id,'stage':stage,'at':datetime.now(timezone.utc).isoformat(),
            'monotonic':stamp,'previous_stage_ms':elapsed,
            'shutter_acknowledged':stage=='shutter_acknowledged' or bool(same_capture and stage!='preflight' and previous.get('shutter_acknowledged'))}
        if log:
            logging.getLogger('uvicorn.error').info('sony_capture capture_id=%s stage=%s at=%s previous_stage_ms=%s',capture_id,stage,self.capture_progress['at'],elapsed)
        if jpeg_bytes is not None:
            self.capture_progress={**self.capture_progress,'jpeg_bytes':jpeg_bytes}
            logging.getLogger('uvicorn.error').info('sony_jpeg_received capture_id=%s bytes=%s transfer_ms=%s',capture_id,jpeg_bytes,elapsed)

    def get_capabilities(self):
        return CameraCapabilities('sony_zve10', 'Sony ZV-E10 — Windows WIA/PTP, hardware NOT VERIFIED',
                                  False, True, True, True, True, 'camera_original', False)

    def get_status(self):
        return {'connected':self.connected, 'previewing':self.previewing,
                'model':self.model, 'hardware_verified':False}

    def _command(self, operation, params=(), *, deadline, data=None, limit=65536):
        if time.monotonic() >= deadline:raise CameraError('timeout', 'Sony operation deadline exceeded.')
        try:
            return self.transport.command(operation, params, data=data, limit=limit, deadline=deadline)
        except CameraError as error:
            if error.code in ('disconnected', 'timeout', 'transport_failed', 'worker_stalled'):
                self.connected = self.previewing = False
                self.fresh_captures.clear()
                # Discard the dead WIA root before the next explicit connect,
                # rather than reusing its old COM session after USB recovery.
                if error.code == 'worker_stalled':
                    raise
                try:self.transport.close()
                except OSError:pass
            raise

    def _properties(self, deadline):
        self.properties = property_info(self._command(0x9209, deadline=deadline, limit=1024*1024))
        return self.properties

    @staticmethod
    def _value(properties, code):
        prop = properties.get(code)
        if not prop or not prop['enabled']:
            raise CameraError('not_ready', f'Sony property 0x{code:04X} unavailable; check still-photo/PC Remote mode.')
        return prop['value']

    def connect(self):
        with self.lock:
            if self.connected:return
            if not self.root:raise CameraError('configuration', 'Sony recovery storage root is not configured.', stage='connect')
            deadline = time.monotonic()+self.timeout
            try:
                self.transport.open(deadline)
                # Retry only the read-only GetDeviceInfo on the same WIA root.
                for delay in (0.15, 0.35, 0.75, None):
                    try:
                        identity = self._command(0x1001, deadline=deadline)
                        break
                    except CameraError as error:
                        if error.code != 'busy' or delay is None or deadline-time.monotonic() <= delay:
                            raise
                        time.sleep(delay)
                info = device_info(identity)
                if info['model'] != 'ZV-E10' or 'SONY' not in info['manufacturer'].upper():
                    raise CameraError('unsupported', f"Expected original Sony ZV-E10; detected {info['model'][:80]!r}. Other models, including ZV-E10M2, are not supported.", stage='connect')
                required_ops = {0x1008, 0x1009, 0x9201, 0x9202, 0x9207, 0x9209}
                if not required_ops.issubset(info['operations']):
                    raise CameraError('unsupported', 'ZV-E10 does not advertise the required PTP operations.', stage='connect')
                for phase in (1, 2):self._command(0x9201, (phase,0,0), deadline=deadline)
                while True:
                    data = self._command(0x9202, (0x00c8,), deadline=deadline)
                    if data:break
                    self._wait(deadline)
                reader = Reader(data)
                version = reader.number(2)
                props, controls = reader.array(), reader.array()
                if version != 0x00c8 or not {HALF_RELEASE,SHUTTER_RELEASE}.issubset(controls) or not {FILE_INFO,LIVE_STATUS,SAVE_DESTINATION,FOCUS_MODE,0x5004,0x5013}.issubset(props):
                    raise CameraError('unsupported', 'Camera does not advertise the required ZV-E10 PTP 2 profile.', stage='connect')
                self._command(0x9201, (3,0,0), deadline=deadline)
                self._properties(deadline)
                self.root.mkdir(parents=True, exist_ok=True)
                self.unresolved = {p for p in self.root.glob('*.json')
                                   if json.loads(p.read_text(encoding='utf-8')).get('status') not in ('saved','cancelled','superseded')}
                self.model, self.connected = info['model'], True
            except Exception:
                self.disconnect()
                raise

    def disconnect(self):
        with self.lock:
            self.connected = self.previewing = False
            self.fresh_captures.clear()
            self.preview_limit = 0
            self.preview_status_until = 0
            self.transport.close()

    def start_live_view(self):
        with self.lock:
            self._ready()
            self.previewing = True  # No guessed 'enable' command: camera controls D221.

    def stop_live_view(self):
        with self.lock:
            self.previewing = False
            self.preview_status_until = 0

    def _ready(self):
        if not self.connected:raise CameraError('disconnected', 'Sony camera is not connected.')

    def get_preview_frame(self):
        started=time.perf_counter()
        with self.lock:
            timings={'driver_lock_ms':round((time.perf_counter()-started)*1000,2)}
            self._ready()
            if not self.previewing:raise CameraError('not_ready', 'Sony Live View was not requested.', stage='preview')
            deadline = time.monotonic()+min(3, self.timeout)
            step=time.perf_counter()
            # Only reuse a positive Live View status while fresh, validated
            # frames keep arriving. Any error forces a full check next time.
            valid_until = self.preview_status_until
            self.preview_status_until = 0
            if time.monotonic() >= valid_until:
                if self._value(self._properties(deadline), LIVE_STATUS) != 1:
                    raise CameraError('not_ready', 'Camera Live View is temporarily unavailable; check still-photo mode.', stage='preview')
                valid_until = time.monotonic() + 0.5
            timings['properties_ms']=round((time.perf_counter()-step)*1000,2)
            step=time.perf_counter()
            if not self.preview_limit:
                info = object_info(self._command(0x1008, (LIVE,), deadline=deadline))
                self.preview_limit = min(info['size'], 8*1024*1024)
            timings['object_info_ms']=round((time.perf_counter()-step)*1000,2)
            wait = self.next_preview - time.monotonic()
            if wait > 0:
                if time.monotonic()+wait >= deadline:raise CameraError('busy', 'Waiting for the next Sony Live View frame.', stage='preview')
                time.sleep(wait)
            self.next_preview = time.monotonic()+0.034  # Sony PTP 2 p.31: <=30 fps.
            step=time.perf_counter()
            data = self._command(0x1009, (LIVE,), deadline=deadline, limit=self.preview_limit)
            acquired_at=time.time()
            timings['acquisition_ms']=round((time.perf_counter()-step)*1000,2)
            worker_ms=getattr(self.transport,'last_worker_ms',None)
            if worker_ms is not None:
                timings['wia_worker_ms']=round(worker_ms,2)
                timings['wia_ipc_overhead_ms']=round(max(0,timings['acquisition_ms']-worker_ms),2)
            step=time.perf_counter()
            reader = Reader(data)
            offset, size = reader.number(4), reader.number(4)
            if offset < 8 or size == 0 or offset+size > len(data):
                raise CameraError('preview', 'Invalid Sony Live View JPEG range.', stage='preview')
            jpeg = data[offset:offset+size]
            check_jpeg(jpeg, preview=True)
            self.preview_status_until = valid_until
            timings['validation_ms']=round((time.perf_counter()-step)*1000,2)
            self.sequence += 1
            return PreviewFrame(jpeg, self.sequence, acquired_at, timings)

    def _paths(self, capture_id):
        capture_id = str(uuid.UUID(capture_id))
        return self.root/(capture_id+'.json'), self.root/(capture_id+'.jpg')

    def _record(self, path, record):
        atomic_write(path, json.dumps(record, sort_keys=True).encode())
        if record.get('status') in ('saved','cancelled','superseded'):
            self.unresolved.discard(path);self.fresh_captures.discard(path.stem)
        else:self.unresolved.add(path)

    def _pending(self):
        return self.unresolved

    def check_capture_abandonment(self):
        # Only called for an explicit Booth start. Do not poll the USB device
        # or modify any receipt to tell the operator about a known blocker.
        self.require_unassigned_recovery_complete()
        for journal in tuple(self.unresolved):
            record=json.loads(journal.read_text(encoding='utf-8'))
            if (record.get('status')=='dispatched' and record.get('abandonment_requested_at')
                    and not self._expected_hash(record) and not (record.get('object') and record.get('transfer_attempted'))):
                raise CameraError('camera_recovery_pending',
                    'Camera capture is blocked by an earlier shot whose JPEG has not been isolated. Ask the Host operator to reconcile it before taking another photo.',
                    stage='capture',shutter_dispatched=False)

    @staticmethod
    def _expected_hash(record):
        values=[record[name] for name in ('sha256','received_sha256') if record.get(name) is not None]
        if any(not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value) for value in values) or len(set(values))>1:
            raise CameraError('recovery_required','Checksum trong receipt không nhất quán. Giữ nguyên ảnh và nhờ Host kiểm tra; không gửi shutter mới.',stage='transfer')
        return values[0] if values else None

    def _observe_identity(self, reference, record, info):
        expected=record.get('object') or {}
        evidence={'expected':expected,'observed':info,
            'changed_fields':sorted(k for k in set(expected)|set(info) if expected.get(k)!=info.get(k))}
        payload=json.dumps(evidence,sort_keys=True).encode()
        path=self.root/'identity-evidence'/(reference+'-'+hashlib.sha256(payload).hexdigest()+'.json')
        if not path.exists():atomic_write(path,payload)
        record['identity_conflict']={**evidence,'path':path.relative_to(self.root.parent.parent).as_posix(),
            'checked_at':datetime.now(timezone.utc).isoformat()}
        self._record(self._paths(reference)[0],record)

    def _restore_rejected(self, capture_id, record):
        """Read back exact, checksum-bound bytes rejected by an older validator.

        No USB commands. Malformed payloads remain rejected; only a completely
        decodable JPEG/MPO with the recorded size/hash can enter recovery cache.
        """
        evidence=record.get('rejected_transfer')
        if not evidence:return
        if not isinstance(evidence,dict):
            raise CameraError('recovery_required','Bằng chứng transfer cũ không hợp lệ; nhờ Host kiểm tra receipt.',stage='transfer')
        digest=evidence.get('sha256','')
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise CameraError('transfer','Checksum bản lưu transfer không hợp lệ; giữ nguyên dữ liệu để kiểm tra.',stage='transfer')
        expected=self._expected_hash(record)
        if expected and expected!=digest:
            raise CameraError('recovery_required','Bản transfer giữ lại không khớp identity đã lưu. Giữ nguyên cả hai bằng chứng để Host khôi phục.',stage='transfer')
        candidate=self.root/'rejected'/(str(uuid.UUID(capture_id))+'-'+digest+'.bin')
        if evidence.get('path')!=candidate.relative_to(self.root.parent.parent).as_posix() or candidate.resolve()!=candidate.absolute():
            raise CameraError('transfer','Đường dẫn bản lưu transfer không hợp lệ; chưa đọc ảnh hoặc gửi shutter.',stage='transfer')
        if not candidate.is_file():
            raise CameraError('transfer','Không tìm thấy bản lưu transfer cũ; nhờ Host khôi phục file.',stage='transfer')
        with candidate.open('rb') as stream:data=stream.read(MAX_TRANSFER+1)
        if len(data)>MAX_TRANSFER or len(data)!=evidence.get('bytes') or len(data)!=(record.get('object') or {}).get('size') or hashlib.sha256(data).hexdigest()!=digest:
            raise CameraError('transfer','Bản lưu transfer không khớp kích thước/checksum; không dùng làm ảnh.',stage='transfer')
        try:check_jpeg(data)
        except CameraError:return  # Still invalid; permit retry of the same camera object only.
        record['recovered_transfer']={'path':evidence['path'],'sha256':digest}
        record['received_sha256']=digest
        self._record(self._paths(capture_id)[0],record)
        self.transfer_cache[capture_id]=data
        self.transfer_hashes[capture_id]=digest

    def reconcile_previous_captures(self, successor_id, deadline, *, exclude=()):
        """Preflight old test/orphan receipts, under the existing camera owner.

        Never presses the shutter or infers physical completion from an empty
        buffer. Host rows are handled separately so completed/current sessions
        cannot be retired by this receipt-only path.
        """
        with self.lock:
            self._ready()
            self.require_unassigned_recovery_complete()
            successor_id=str(uuid.UUID(successor_id))
            excluded=set(exclude)
            results=[]
            for journal in sorted(self.root.glob('*.json')):
                if journal.stem in excluded:continue
                record=json.loads(journal.read_text(encoding='utf-8'))
                if record.get('status') in ('saved','cancelled'):continue
                capture_id=str(uuid.UUID(journal.stem))
                original_session=record.get('session_id') or capture_id
                preserved=self.supersede_capture(capture_id,original_session,successor_id,deadline)
                results.append({'capture_id':capture_id,'original':preserved})
            # Also reject a late/unclaimed image after an earlier cancellation.
            # Do not consume or label it as a new session's photograph.
            if self._value(self._properties(deadline),FILE_INFO)!=0:
                raise CameraError('camera_recovery_pending','Camera contains an unclaimed image after reconciliation. Preserve it; no new shutter was sent.',stage='transfer',uncertain=True)
            return results

    def supersede_capture(self, capture_id, session_id, successor_id, deadline):
        """Quarantine a retired capture under the controller's exclusive I/O lease.

        Never sends shutter-down; may finish the existing journaled release.
        Unknown physical outcomes remain barriers. Empty
        tombstones are rechecked before subsequent shutters for late old JPEGs.
        """
        with self.lock:
            self._ready()
            session_id,successor_id=str(uuid.UUID(session_id)),str(uuid.UUID(successor_id))
            journal,saved=self._paths(capture_id)
            if not journal.is_file():return None
            record=json.loads(journal.read_text(encoding='utf-8'))
            if record.get('status')=='cancelled':return None
            if record.get('session_id',session_id)!=session_id:
                raise CameraError('recovery_required','Receipt camera không khớp phiên cũ; chưa gửi shutter mới.')
            retired_empty=(record.get('status')=='superseded' and record.get('release_pending') is False
                and not record.get('half_release_pending')
                and bool(record.get('object')) and bool(record.get('superseded_by'))
                and record.get('capture_outcome')=='buffer_empty_original_unavailable'
                and bool(record.get('buffer_checked_at')))
            if not record.get('superseded_by'):
                archive=self.root/'superseded'/journal.name
                if not archive.exists():atomic_write(archive,journal.read_bytes())
                record.update(session_id=session_id,superseded_by=successor_id,
                    superseded_at=datetime.now(timezone.utc).isoformat(),
                    supersede_reason='New session acquired camera after previous capture stopped.')
                self._record(journal,record)
            if record.get('release_pending') is not False or record.get('half_release_pending'):
                # Reuse the existing safe recovery: release (value 1), never a
                # new press (value 2). A WIA failure leaves the receipt pending.
                self.recover_capture(capture_id,deadline,quarantine=True)
                record=json.loads(journal.read_text(encoding='utf-8'))
            if record.get('shutter_not_dispatched') is True:
                self._close_undispatched_capture(journal,record,deadline)
                return None
            destination=self.root.parent/session_id/(str(uuid.UUID(capture_id))+'.jpg')
            if destination.exists():
                data=destination.read_bytes();check_jpeg(data)
                if not record.get('sha256') or hashlib.sha256(data).hexdigest()!=record['sha256']:
                    raise CameraError('transfer','JPEG cách ly không khớp receipt; giữ nguyên file để khôi phục.',stage='transfer')
            else:
                if not saved.exists() and capture_id not in self.transfer_cache:self._restore_rejected(capture_id,record)
                cached=saved.exists() or capture_id in self.transfer_cache
                count=self._value(self._properties(deadline),FILE_INFO)
                if record.get('last_buffer_value')!=count:
                    record['last_buffer_value']=count;self._record(journal,record)
                if not cached and count==0:
                    if retired_empty:
                        # Honor a completed, audited legacy handoff even when
                        # its receipt predates transfer_attempted. The live WIA
                        # query above must STILL succeed and report empty.
                        self.unresolved.discard(journal)
                        self.fresh_captures.discard(capture_id)
                        return None
                    if not self._expected_hash(record) and not (record.get('object') and record.get('transfer_attempted')):
                        # An empty buffer before any GetObject is not proof an
                        # uncertain exposure finished. A late A could otherwise
                        # be consumed by B's first transfer after a new press.
                        detail = ('Host đã ghi nhận bỏ ảnh cũ, nhưng chưa cô lập được JPEG có thể đến muộn.'
                                  if record.get('abandonment_requested_at') else
                                  'Chưa xác minh lệnh chụp cũ đã kết thúc. Nhờ Host kiểm tra biên nhận cũ.')
                        raise CameraError('camera_recovery_pending',f'{detail} Buffer rỗng chưa đủ để chụp phiên mới; chưa gửi shutter mới.',stage='transfer')
                    # GetObject may already have consumed a previous transfer.
                    # ObjectInfo is not evidence that the camera is still busy.
                    # Keep its metadata, and explicitly audit the missing local
                    # original instead of pretending a JPEG was saved/recovered.
                    record.update(status='superseded',buffer_checked_at=datetime.now(timezone.utc).isoformat(),
                        capture_outcome='buffer_empty_original_unavailable' if record.get('object') else 'buffer_empty_no_image')
                    self._record(journal,record)
                    return None
                if not cached and not (count & 0x8000 and count & 0x7fff):
                    raise CameraError('camera_recovery_pending',f'Camera chưa báo JPEG cũ sẵn sàng (FILE_INFO=0x{count:04X}). Đợi camera hoàn tất hoặc nhờ Host kiểm tra; chưa gửi shutter mới.',stage='transfer')
                data=self.get_captured_photo(capture_id,deadline,quarantine=True).data
                atomic_write(destination,data)
                record=json.loads(journal.read_text(encoding='utf-8'))
            record.update(status='superseded',quarantine_path=destination.relative_to(self.root.parent.parent).as_posix(),
                sha256=hashlib.sha256(data).hexdigest())
            self._record(journal,record)
            self.transfer_cache.pop(capture_id,None)
            self.transfer_hashes.pop(capture_id,None)
            return {'path':record['quarantine_path'],'sha256':record['sha256'],'mime':'image/jpeg'}

    def _unassigned_pending(self):
        return [p for p in (self.root/'unassigned').glob('*.json')
                if json.loads(p.read_bytes()).get('status')!='preserved']

    def require_unassigned_recovery_complete(self):
        if self._unassigned_pending():
            raise CameraError('camera_recovery_pending','The operator must finish verifying the preserved Sony buffer before a new shutter.',shutter_dispatched=False)

    def preserve_unassigned_buffer(self, capture_id, deadline, *, known_hashes):
        """Preserve one ready buffer object without assigning it to any slot."""
        with self.lock:
            self._ready()
            journal,_=self._paths(capture_id)
            record=json.loads(journal.read_bytes())
            if (record.get('status')!='superseded' or not record.get('buffer_checked_at')
                    or record.get('capture_outcome')!='buffer_empty_original_unavailable'
                    or record.get('release_pending') is not False or record.get('half_release_pending')
                    or not (record.get('identity_conflict') or {}).get('observed')):
                raise CameraError('recovery_required','Use the original capture recovery unless there is an unmatched JPEG and a retired, previously drained receipt.')
            if self.unresolved:
                raise CameraError('recovery_required','Resolve the outstanding Sony receipt before preserving an unassigned image.')

            directory=self.root/'unassigned'
            pending=self._unassigned_pending()
            props=self._properties(deadline)
            count=self._value(props,FILE_INFO)
            if pending:
                if len(pending)!=1:raise CameraError('recovery_required','Multiple unfinished buffer recovery records need inspection.')
                audit=pending[0]
                evidence=json.loads(audit.read_bytes())
                if evidence['blocking_receipt']!=capture_id:
                    raise CameraError('recovery_required','Finish the existing buffer recovery first.')
            else:
                if count==0:
                    completed=[json.loads(path.read_bytes()) for path in directory.glob('*.json')]
                    for prior in completed:
                        if prior.get('blocking_receipt')==capture_id and prior.get('buffer_drained'):
                            original=directory/(prior['recovery_id']+'.jpg')
                            if hashlib.sha256(original.read_bytes()).hexdigest()!=prior['sha256']:
                                raise CameraError('recovery_required','Previously preserved JPEG differs from its recorded checksum.')
                            return prior
                    raise CameraError('recovery_required','Buffer is empty today, but there is no verified preservation for this JPEG.')
                if count!=0x8001:
                    raise CameraError('recovery_required',f'Expected one ready Sony JPEG; FILE_INFO=0x{count:04X}.')
                info=object_info(self._command(0x1008,(SHOT,),deadline=deadline))
                if (info['format']!=0x3801 or not info['name'].lower().endswith(('.jpg','.jpeg'))
                        or info!=(record.get('identity_conflict') or {}).get('observed')):
                    raise CameraError('recovery_required','The current ObjectInfo differs from the recorded unmatched JPEG; preserve the camera buffer for inspection.')
                if shutil.disk_usage(self.root).free<=info['size']:
                    raise CameraError('recovery_required','Insufficient space to preserve the buffered original.')
                recovery_id=str(uuid.uuid4())
                audit=directory/(recovery_id+'.json')
                evidence={'recovery_id':recovery_id,'status':'transfer_started','blocking_receipt':capture_id,
                          'old_object':record['object'],'observed_object':info,'file_info_before':count,
                          'save_destination':self._value(props,SAVE_DESTINATION),
                          'started_at':datetime.now(timezone.utc).isoformat()}
                atomic_write(audit,json.dumps(evidence,sort_keys=True).encode())
                # Journal before GetObject, which may consume the camera's copy.
                data=self._command(0x1009,(SHOT,),deadline=deadline,limit=info['size'])
                atomic_write(audit.with_suffix('.bin'),data)

            staged=audit.with_suffix('.bin')
            original=audit.with_suffix('.jpg')
            if not staged.is_file() and not original.is_file():
                raise CameraError('recovery_required','The previous buffer read was interrupted before bytes were saved. Preserve all evidence; GetObject was not retried.')
            data=(original if original.is_file() else staged).read_bytes()
            dimensions=check_jpeg(data)
            info=evidence['observed_object']
            if len(data)!=info['size'] or any(info[key]>0 and info[key]!=dimension
                                             for key,dimension in zip(('width','height'),dimensions)):
                raise CameraError('recovery_required','Preserved payload differs from the Sony ObjectInfo; it was retained for inspection.')
            digest=hashlib.sha256(data).hexdigest()
            if not original.exists():staged.rename(original)
            after=self._value(self._properties(deadline),FILE_INFO)
            if after!=0:
                raise CameraError('recovery_required',f'Original preserved, but the camera buffer is still occupied (FILE_INFO=0x{after:04X}).')
            evidence.update(status='preserved',sha256=digest,dimensions=list(dimensions),buffer_drained=True,
                file_info_after=after,original_path=original.relative_to(self.root.parent.parent).as_posix(),
                matched_capture_ids=sorted(known_hashes.get(digest,())),attribution='unassigned',
                verified_at=datetime.now(timezone.utc).isoformat())
            atomic_write(audit,json.dumps(evidence,sort_keys=True).encode())
            return evidence

    def cancel_capture(self, capture_id, deadline, *, confirm_discard=False, isolation_step=None):
        """Abandon one receipt after the operator's offline/online isolation checks."""
        if not confirm_discard:raise CameraError('confirmation_required','Explicit discard confirmation is required.')
        with self.lock:
            if isolation_step!='power_off':self._ready()
            journal,saved=self._paths(capture_id)
            if not journal.is_file():raise CameraError('recovery_required','No receipt for this capture; nothing was cancelled.')
            record=json.loads(journal.read_text(encoding='utf-8'))
            if record.get('status')=='cancelled':return record
            if (record.get('status')!='dispatched' or record.get('object') is not None
                    or self._expected_hash(record) or record.get('transfer_attempted')
                    or record.get('rejected_transfer') or record.get('quarantine_path')
                    or saved.exists() or capture_id in self.transfer_cache):
                raise CameraError('recovery_required','Capture may contain a saved/received JPEG. Preserve and recover it; cancellation was refused.')
            if record.get('release_pending') is not False or record.get('half_release_pending'):
                raise CameraError('recovery_required','Shutter release is unresolved. No camera command or cancellation was sent.')
            archive=self.root/'abandonment'/journal.name
            if isolation_step is not None and (not record.get('abandonment_requested_at') or not archive.is_file()):
                raise CameraError('recovery_required','Record the operator abandonment and preserve its original receipt before isolating the camera.')
            if isolation_step=='power_off':
                if self.connected:raise CameraError('recovery_required','The WIA session must be closed before recording camera power-off.')
                if not record.get('isolation_power_off_at'):
                    record['isolation_power_off_at']=datetime.now(timezone.utc).isoformat()
                    self._record(journal,record)
                return record
            props=self._properties(deadline)
            if self._value(props,FILE_INFO)!=0:
                raise CameraError('recovery_required','Camera still contains an unclaimed image. Recover the existing capture; no cancellation or new shutter was sent.')
            if isolation_step=='verify_reconnect':
                if not record.get('isolation_power_off_at'):
                    raise CameraError('recovery_required','First record the disconnected, unpowered camera with its old memory card removed.')
                destination=self._value(props,SAVE_DESTINATION)
                if destination!=1:
                    raise CameraError('recovery_required',f'Set Sony Still Img. Save Dest. to PC Only while the old memory card stays out (PTP 0xD222=0x{destination:04X}).')
                record.update(status='cancelled',physical_outcome='uncertain',
                    isolation_method='cold_power_off_without_old_media',last_buffer_value=0)
                # Archive the verified decision before publishing the same one
                # to the live receipt. The Host replays it into SQLite on boot.
                decision=self.root/'cancelled'/journal.name
                if decision.exists():
                    previous=json.loads(decision.read_bytes())
                    verified_at=previous.pop('isolation_verified_at',None)
                    if not verified_at or previous!=record:
                        raise CameraError('recovery_required','Cancellation archive differs; preserve both records for inspection.')
                    record['isolation_verified_at']=verified_at
                else:
                    record['isolation_verified_at']=datetime.now(timezone.utc).isoformat()
                    atomic_write(decision,json.dumps(record,sort_keys=True).encode())
                self._record(journal,record)
                return record
            if record.get('abandonment_requested_at'):return record
            original=journal.read_bytes()
            if archive.exists():
                if archive.read_bytes()!=original:raise CameraError('recovery_required','Abandonment archive differs; preserve existing records for inspection.')
            else:atomic_write(archive,original)
            # An untagged JPEG could arrive after the next capture's preflight.
            # Keep the dispatched receipt in unresolved until existing
            # reconciliation can prove the old image's identity or isolation.
            record.update(abandonment_requested_at=datetime.now(timezone.utc).isoformat(),
                abandonment_reason='Operator chose to abandon the image; buffer was empty at inspection.',
                physical_outcome='uncertain')
            self._record(journal,record)
            return record

    def capture_persisted(self, capture_id):
        # Only the extra recovery cache is discarded, AFTER the controller has
        # durably saved the original and its slot. The receipt remains. Normal
        # session cleanup continues to own the official temporary original.
        with self.lock:
            _, cached = self._paths(capture_id)
            try:cached.unlink(missing_ok=True)
            except OSError:pass  # Retaining a redundant cache must not fail a saved capture.
            self.transfer_cache.pop(str(uuid.UUID(capture_id)),None)
            self.transfer_hashes.pop(str(uuid.UUID(capture_id)),None)

    @staticmethod
    def _wait(deadline):
        remaining = deadline-time.monotonic()
        if remaining <= 0:raise CameraError('timeout', 'Timed out waiting for the captured Sony JPEG.', stage='transfer')
        time.sleep(min(0.1, remaining))

    def _wait_focus(self, deadline):
        # libgphoto2 camera_sony_capture: AF holds the button for focus/image
        # readiness, at most one second. MF needs no focus wait. USB commands
        # retain the overall deadline; do not create an artificial USB timeout.
        end=min(deadline,time.monotonic()+1)
        while time.monotonic()<end:
            props=self._properties(deadline)
            focus=props.get(FOCUS_FOUND,{})
            count=self._value(props,FILE_INFO)
            if (focus.get('enabled') and focus.get('value') in (2,3)) or (count & 0x8000 and count & 0x7fff):return
            remaining=end-time.monotonic()
            if remaining>0:time.sleep(min(0.1,remaining))

    def _wait_buffer_drained(self, journal, record, deadline):
        # Only after the exact original has been validated and durably cached.
        # Never GetObject again to discard an occupied/unknown camera buffer.
        # Button control descriptors are not a verified physical idle sensor. Readiness
        # here requires the known JPEG AND journaled release ACKs, not ACK alone.
        self._capture_stage(journal.stem,'buffer_drain')
        if record.get('release_pending') is not False or record.get('half_release_pending'):
            raise CameraError('recovery_required','Sony shutter release is unconfirmed. Recover the same capture; no new shutter was sent.',stage='transfer')
        try:
            while True:
                try:
                    props=self._properties(deadline)
                    count=self._value(props,FILE_INFO)
                except CameraError as error:
                    if error.code!='busy':raise
                    self._wait(deadline);continue
                if record.get('last_buffer_value')!=count:
                    record['last_buffer_value']=count;self._record(journal,record)
                if count==0:return
                self._wait(deadline)
        except CameraError as error:
            if error.code=='timeout':
                raise CameraError('timeout','Original Sony JPEG is saved, but camera buffer readiness is unverified. Retry the same capture; no new shutter was sent.',stage='transfer') from error
            raise

    def capture_photo(self, capture_id, deadline):
        with self.lock:
            journal, _ = self._paths(capture_id)
            try:
                self._ready()
                self.require_unassigned_recovery_complete()
                if journal.exists():return self.recover_capture(capture_id, deadline)
                if self._pending():
                    raise CameraError('recovery_required', 'A previous Sony capture is unresolved. Recover that same capture before taking another photo.')
                self._capture_stage(capture_id,'preflight')
                props = self._properties(deadline)
                if self._value(props, FILE_INFO) != 0:
                    raise CameraError('recovery_required', 'Camera already contains an unclaimed capture buffer. Preserve/recover it with the original capture request.')
                # D2C1/D2C2 describe button controls, not a verified shutter-state
                # readback. Unknown intents are blocked by _pending() above;
                # completed intents require a validated original and drained buffer.
                if self._value(props, 0x5013) != 1:
                    raise CameraError('camera_mode', 'Set Sony Drive Mode to Single Shooting before capture.')
                if self._value(props, 0x5004) not in (1,2,3,4):
                    raise CameraError('camera_mode', 'Set still-image File Format to JPEG (not RAW/HEIF) and PC Save Image Size to Original.')
                if self._value(props, SAVE_DESTINATION) not in (1,0x11):
                    raise CameraError('camera_mode', 'Set Still Img. Save Dest. to PC Only or PC+Camera; PC Save Image Size: Original.')
                focus_mode=self._value(props,FOCUS_MODE)
            except CameraError as error:
                error.shutter_dispatched = False
                raise
            logging.getLogger('uvicorn.error').info('sony_capture_preflight capture_id=%s focus_mode=%s',capture_id,focus_mode)
            # Ordinary press/release uses D2C2. D2C7 (RequestOneShooting)
            # is a different control, not the normal shutter button.
            record = {'status':'dispatched', 'object':None, 'release_pending':True,
                'shutter_control':SHUTTER_RELEASE, 'half_release_pending':True}
            self._record(journal, record)  # Durable intent BEFORE the physical command.
            self.fresh_captures.add(str(uuid.UUID(capture_id)))
            shutter_dispatched = False
            try:
                self._capture_stage(capture_id,'shutter_press')
                self._command(0x9207, (HALF_RELEASE,), data=struct.pack('<H',2), deadline=deadline)
                self._capture_stage(capture_id,'shutter_dispatch',log=False)
                shutter_dispatched = None
                self._command(0x9207, (SHUTTER_RELEASE,), data=struct.pack('<H',2), deadline=deadline)
                shutter_dispatched = True
                self._capture_stage(capture_id,'shutter_acknowledged',log=False)
                if focus_mode!=1:self._wait_focus(deadline)
                self.recover_capture(capture_id,deadline)  # Release only; never press twice.
            except CameraError as error:
                if shutter_dispatched is False:
                    # Half-press may still need release. Only this live error
                    # path proves that the full-press command was never sent.
                    record.update(shutter_not_dispatched=True,release_pending=False)
                    self._record(journal,record)
                error.uncertain = shutter_dispatched is not False
                error.shutter_dispatched = shutter_dispatched
                raise
            # Controller journals this reference before it waits/downloads.
            return str(uuid.UUID(capture_id))

    def _close_undispatched_capture(self, journal, record, deadline):
        if self._value(self._properties(deadline),FILE_INFO)!=0:
            raise CameraError('camera_recovery_pending','Unexpected Sony image after a failed half-press; preserve the buffer.',
                stage='transfer',shutter_dispatched=False)
        if record.get('status')!='superseded':
            record.update(status='superseded',capture_outcome='shutter_not_dispatched',
                buffer_checked_at=datetime.now(timezone.utc).isoformat(),last_buffer_value=0)
            self._record(journal,record)

    def recover_capture(self, capture_id, deadline, *, quarantine=False):
        """Read/reconcile an existing intent. Never sends a shutter-down."""
        with self.lock:
            self._ready()
            journal, _ = self._paths(capture_id)
            if not journal.is_file():raise CameraError('recovery_required', 'No durable Sony capture receipt; cannot safely retry shutter.', uncertain=True)
            record = json.loads(journal.read_text(encoding='utf-8'))
            if record.get('superseded_by') and not quarantine:
                raise CameraError('capture_superseded','Yêu cầu này thuộc phiên cũ đã được thay thế. Ảnh cũ được giữ riêng; không chụp lại yêu cầu cũ.')
            if record.get('status')=='cancelled':
                raise CameraError('capture_cancelled','The previous capture was cancelled by the operator. Saved photos are unchanged; choose a new capture explicitly.',stage='capture')
            if record.get('release_pending') or record.get('half_release_pending'):
                self._capture_stage(capture_id,'shutter_release')
                # Old receipts used D2C7. Release only the journaled control;
                # recovery must never press again or switch an old intent.
                control=record.get('shutter_control',ONE_SHOT)
                if type(control) is not int or control not in (ONE_SHOT,SHUTTER_RELEASE):
                    raise CameraError('recovery_required','Unknown shutter control in Sony receipt; preserve it for Host recovery. No camera command sent.',uncertain=True)
                if record.get('half_release_pending') and control!=SHUTTER_RELEASE:
                    raise CameraError('recovery_required','Inconsistent Sony button receipt; preserve it for Host recovery. No camera command sent.',uncertain=True)
                if record.get('release_pending'):
                    self._command(0x9207, (control,), data=struct.pack('<H',1), deadline=deadline)
                    record['release_pending'] = False
                    self._record(journal, record)
                if record.get('half_release_pending'):
                    self._command(0x9207, (HALF_RELEASE,), data=struct.pack('<H',1), deadline=deadline)
                    record['half_release_pending'] = False
                    self._record(journal, record)
            if record.get('shutter_not_dispatched') is True and not quarantine:
                self._close_undispatched_capture(journal,record,deadline)
                error=CameraError('capture_not_dispatched','The previous full shutter was never sent. Start a new capture.',
                    shutter_dispatched=False)
                error.clear_pending=True
                raise error
            return str(uuid.UUID(capture_id))

    def get_captured_photo(self, reference, deadline, *, quarantine=False):
        with self.lock:
            self._ready()
            journal, saved = self._paths(reference)
            self.recover_capture(reference, deadline,quarantine=quarantine)
            record = json.loads(journal.read_text(encoding='utf-8'))
            if not saved.exists() and reference not in self.transfer_cache:self._restore_rejected(reference,record)
            expected_hash=self._expected_hash(record)
            observed_info=None
            if saved.exists() or reference in self.transfer_cache:
                checkpoint_missing=not expected_hash
                if checkpoint_missing and not saved.exists():
                    # Only our already-received RAM payload has this digest.
                    # Never derive trust from a hashless file, name or metadata.
                    expected_hash=self._expected_hash({'received_sha256':self.transfer_hashes.get(reference)})
                if not expected_hash:
                    raise CameraError('recovery_required','File cache chưa có checksum để chứng minh đúng capture. Giữ file và nhờ Host khôi phục; không chụp lại cùng yêu cầu.',stage='transfer')
                data = saved.read_bytes() if saved.exists() else self.transfer_cache[reference]
                dimensions=check_jpeg(data)
                if len(data) != record['object']['size']:
                    raise CameraError('transfer', 'Sony recovery JPEG size mismatch.', stage='transfer')
                digest=hashlib.sha256(data).hexdigest()
                if digest != expected_hash:
                    raise CameraError('transfer', 'Sony recovery JPEG checksum mismatch.', stage='transfer')
                if checkpoint_missing:
                    record['received_sha256']=expected_hash
                    self._record(journal,record)  # Retry durability BEFORE reporting success.
                if not saved.exists():atomic_write(saved,data)
            else:
                self._capture_stage(reference,'waiting_buffer')
                polls=0
                try:
                    while True:
                        count = self._value(self._properties(deadline), FILE_INFO)
                        polls+=1
                        self.capture_progress={**self.capture_progress,'buffer_polls':polls,'last_buffer_value':count}
                        if record.get('last_buffer_value')!=count:
                            record['last_buffer_value']=count;self._record(journal,record)
                        if count & 0x8000 and count & 0x7fff:break
                        self._wait(deadline)
                except CameraError as error:
                    # A release ACK without any identified JPEG does not prove
                    # the physical exposure happened or finished. Keep this
                    # intent pending and make that uncertainty explicit to Host.
                    logging.getLogger('uvicorn.error').warning(
                        'sony_buffer_wait_failed capture_id=%s polls=%s last_file_info=%s code=%s connected=%s: %s',
                        reference,polls,self.capture_progress.get('last_buffer_value'),error.code,self.connected,error)
                    error.stage='transfer';error.uncertain=True
                    raise
                self._capture_stage(reference,'object_info')
                info = object_info(self._command(0x1008, (SHOT,), deadline=deadline))
                if info['format'] != 0x3801 or not info['name'].lower().endswith(('.jpg','.jpeg')):
                    self._observe_identity(reference,record,info)
                    raise CameraError('transfer', 'Sony capture buffer is not JPEG. No preview or RAW conversion was substituted.', stage='transfer')
                if record.get('status')=='superseded' and not expected_hash:
                    self._observe_identity(reference,record,info)
                    raise CameraError('recovery_required',f'JPEG trong bộ đệm ({info["name"]}, {info["size"]} byte) chưa xác định được lượt chụp. Nhờ Host lưu riêng bộ đệm cho biên nhận {reference}.',stage='transfer')
                if record['object'] is not None:
                    changed={k for k in set(record['object'])|set(info) if record['object'].get(k)!=info.get(k)}
                    if changed:
                        self._observe_identity(reference,record,info)
                        # Optional geometry may be filled in later, but metadata
                        # alone NEVER proves identity. Require the previously
                        # received byte hash and verify the payload below too.
                        if not expected_hash or changed-{'width','height'}:
                            raise CameraError('recovery_required','Camera buffer changed after interrupted transfer; refusing to assign another photo. Đã giữ metadata khác biệt; nhờ Host khôi phục ảnh gốc, không chụp lại cùng yêu cầu.',stage='transfer')
                    if not expected_hash:
                        self._observe_identity(reference,record,info)
                        raise CameraError('recovery_required','Không thể chứng minh buffer vẫn là ảnh cũ sau transfer gián đoạn. Giữ nguyên receipt; nhờ Host khôi phục hoặc cách ly ảnh, không chụp lại cùng yêu cầu.',stage='transfer')
                else:
                    if not expected_hash and reference not in self.fresh_captures:
                        self._observe_identity(reference,record,info)
                        raise CameraError('recovery_required','Không thể chứng minh ảnh thuộc yêu cầu cũ sau reconnect/restart. Giữ nguyên buffer và receipt; nhờ Host khôi phục hoặc cách ly ảnh.',stage='transfer')
                    record['object']=info
                observed_info=info
                record['transfer_attempted']=True
                self._record(journal, record)
                self._capture_stage(reference,'jpeg_transfer')
                data = self._command(0x1009, (SHOT,), deadline=deadline, limit=info['size'])
                self._capture_stage(reference,'jpeg_validation',jpeg_bytes=len(data))
                try:
                    dimensions=check_jpeg(data)
                    if len(data)!=info['size']:
                        raise CameraError('transfer','Sony original JPEG byte count does not match ObjectInfo.',stage='transfer')
                except CameraError as error:
                    # A transfer can consume the camera buffer even when the
                    # payload is invalid. Retain the exact rejected bytes for
                    # recovery/debugging, but NEVER serve them as a saved photo.
                    digest=hashlib.sha256(data).hexdigest()
                    rejected=self.root/'rejected'/(reference+'-'+digest+'.bin')
                    if not rejected.exists():atomic_write(rejected,data)
                    record['rejected_transfer']={'sha256':digest,'bytes':len(data),
                        'path':rejected.relative_to(self.root.parent.parent).as_posix(),'error':str(error)}
                    self._record(journal,record)
                    raise
                digest=hashlib.sha256(data).hexdigest()
                if expected_hash and digest!=expected_hash:
                    path=self.root/'rejected'/(reference+'-'+digest+'.bin')
                    if not path.exists():atomic_write(path,data)
                    record['unexpected_transfer']={'sha256':digest,'expected_sha256':expected_hash,'bytes':len(data),
                        'path':path.relative_to(self.root.parent.parent).as_posix()}
                    self._record(journal,record)
                    raise CameraError('recovery_required','JPEG nhận lại khác SHA-256 của ảnh cũ. Đã giữ riêng dữ liệu; không gán vào phiên, nhờ Host kiểm tra.',stage='transfer')
                # Hash checkpoint precedes the cache file: a crash cannot leave
                # a seemingly trusted UUID-named JPEG with no byte identity.
                # Keep the received bytes in RAM even if the checkpoint fsync
                # itself fails; an unverified cache still cannot be served.
                self.transfer_cache[reference] = data
                self.transfer_hashes[reference] = digest
                record['received_sha256']=digest
                self._record(journal,record)
                # If local persistence fails after the camera buffer was consumed,
                # retain this one original in memory for retry, without re-firing.
                self._capture_stage(reference,'durable_cache')
                atomic_write(saved, data)
            record['jpeg_dimensions']=list(dimensions)
            info=record['object']
            # ZV-E10 virtual ObjectInfo may omit width/height (zero). The JPEG
            # decoder is authoritative in that case; positive values must match.
            if not quarantine and any(metadata[name]>0 and metadata[name]!=actual
                                      for metadata in (info,observed_info) if metadata is not None
                                      for name,actual in zip(('width','height'),dimensions)):
                record['validation_error']='JPEG dimensions disagree with nonzero ObjectInfo dimensions.'
                self._record(journal,record)
                raise CameraError('transfer','Sony original JPEG has unexpected dimensions; original bytes retained for recovery.',stage='transfer')
            if not record.get('buffer_drained'):
                self._wait_buffer_drained(journal,record,deadline)
                record['buffer_drained']=True
            record.update(status='saved', sha256=digest)
            self._record(journal, record)
            self.transfer_cache.pop(reference,None)
            self.transfer_hashes.pop(reference,None)
            self.fresh_captures.discard(reference)
            self._capture_stage(reference,'original_ready')
            return ValidatedSonyOriginal(data, 'image/jpeg', 'camera_original')
