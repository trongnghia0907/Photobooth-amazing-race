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
from pathlib import Path
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
        self.properties = {}
        self.unresolved = set()
        self.transfer_cache = {}  # At most one unresolved original, bounded to 64 MiB.

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
            if error.code in ('disconnected', 'timeout'):
                self.connected = self.previewing = False
                # Discard the dead WIA root before the next explicit connect,
                # rather than reusing its old COM session after USB recovery.
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
                info = device_info(self._command(0x1001, deadline=deadline))
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
                if version != 0x00c8 or ONE_SHOT not in controls or not {FILE_INFO,LIVE_STATUS,SAVE_DESTINATION,0x5004,0x5013}.issubset(props):
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
            self.preview_limit = 0
            self.transport.close()

    def start_live_view(self):
        with self.lock:
            self._ready()
            self.previewing = True  # No guessed 'enable' command: camera controls D221.

    def stop_live_view(self):
        with self.lock:self.previewing = False

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
            if self._value(self._properties(deadline), LIVE_STATUS) != 1:
                raise CameraError('not_ready', 'Camera Live View is temporarily unavailable; check still-photo mode.', stage='preview')
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
            step=time.perf_counter()
            reader = Reader(data)
            offset, size = reader.number(4), reader.number(4)
            if offset < 8 or size == 0 or offset+size > len(data):
                raise CameraError('preview', 'Invalid Sony Live View JPEG range.', stage='preview')
            jpeg = data[offset:offset+size]
            check_jpeg(jpeg, preview=True)
            timings['validation_ms']=round((time.perf_counter()-step)*1000,2)
            self.sequence += 1
            return PreviewFrame(jpeg, self.sequence, acquired_at, timings)

    def _paths(self, capture_id):
        capture_id = str(uuid.UUID(capture_id))
        return self.root/(capture_id+'.json'), self.root/(capture_id+'.jpg')

    def _record(self, path, record):
        atomic_write(path, json.dumps(record, sort_keys=True).encode())
        if record.get('status') in ('saved','cancelled','superseded'):self.unresolved.discard(path)
        else:self.unresolved.add(path)

    def _pending(self):
        return self.unresolved

    def _restore_rejected(self, capture_id, record):
        """Read back exact, checksum-bound bytes rejected by an older validator.

        No USB commands. Malformed payloads remain rejected; only a completely
        decodable JPEG/MPO with the recorded size/hash can enter recovery cache.
        """
        evidence=record.get('rejected_transfer')
        if not evidence:return
        digest=evidence.get('sha256','')
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise CameraError('transfer','Checksum bản lưu transfer không hợp lệ; giữ nguyên dữ liệu để kiểm tra.',stage='transfer')
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
        self.transfer_cache[capture_id]=data
        record['recovered_transfer']={'path':evidence['path'],'sha256':digest}
        self._record(self._paths(capture_id)[0],record)

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
            if not record.get('superseded_by'):
                record.update(session_id=session_id,superseded_by=successor_id,
                    superseded_at=datetime.now(timezone.utc).isoformat(),
                    supersede_reason='New session acquired camera after previous capture stopped.')
                self._record(journal,record)
            if record.get('release_pending') is not False:
                # Reuse the existing safe recovery: release (value 1), never a
                # new press (value 2). A WIA failure leaves the receipt pending.
                self.recover_capture(capture_id,deadline,quarantine=True)
                record=json.loads(journal.read_text(encoding='utf-8'))
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
            return {'path':record['quarantine_path'],'sha256':record['sha256'],'mime':'image/jpeg'}

    def cancel_capture(self, capture_id, deadline, *, confirm_discard=False):
        """Abandon an empty failed capture; retain its receipt and never fire."""
        if not confirm_discard:raise CameraError('confirmation_required','Explicit discard confirmation is required.')
        with self.lock:
            self._ready()
            journal,saved=self._paths(capture_id)
            if not journal.is_file():raise CameraError('recovery_required','No receipt for this capture; nothing was cancelled.')
            record=json.loads(journal.read_text(encoding='utf-8'))
            if record.get('status')=='cancelled':return record
            if record.get('status')!='dispatched' or record.get('object') is not None or saved.exists() or capture_id in self.transfer_cache:
                raise CameraError('recovery_required','Capture may contain a saved/received JPEG. Preserve and recover it; cancellation was refused.')
            if record.get('release_pending') is not False:
                raise CameraError('recovery_required','Shutter release is unresolved. No camera command or cancellation was sent.')
            if self._value(self._properties(deadline),FILE_INFO)!=0:
                raise CameraError('recovery_required','Camera still contains an unclaimed image. Recover the existing capture; no cancellation or new shutter was sent.')
            archive=self.root/'cancelled'/journal.name
            original=journal.read_bytes()
            if archive.exists():
                if archive.read_bytes()!=original:raise CameraError('recovery_required','Cancellation archive differs; preserve existing records for inspection.')
            else:atomic_write(archive,original)
            record.update(status='cancelled',cancelled_at=datetime.now(timezone.utc).isoformat(),
                cancel_reason='Operator confirmed discard; camera image buffer verified empty.')
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

    @staticmethod
    def _wait(deadline):
        remaining = deadline-time.monotonic()
        if remaining <= 0:raise CameraError('timeout', 'Timed out waiting for the captured Sony JPEG.', stage='transfer')
        time.sleep(min(0.1, remaining))

    def capture_photo(self, capture_id, deadline):
        with self.lock:
            self._ready()
            journal, _ = self._paths(capture_id)
            if journal.exists():return self.recover_capture(capture_id, deadline)
            if self._pending():
                raise CameraError('recovery_required', 'A previous Sony capture is unresolved. Retry that same capture; no new shutter was sent.')
            props = self._properties(deadline)
            if self._value(props, FILE_INFO) != 0:
                raise CameraError('recovery_required', 'Camera already contains an unclaimed capture buffer; no shutter sent. Preserve/recover it with the original capture request.')
            if self._value(props, 0x5013) != 1:
                raise CameraError('camera_mode', 'Set Sony Drive Mode to Single Shooting before capture.')
            if self._value(props, 0x5004) not in (1,2,3,4):
                raise CameraError('camera_mode', 'Set still-image File Format to JPEG (not RAW/HEIF) and PC Save Image Size to Original.')
            if self._value(props, SAVE_DESTINATION) not in (1,0x11):
                raise CameraError('camera_mode', 'Set Still Img. Save Dest. to PC Only or PC+Camera; PC Save Image Size: Original.')
            record = {'status':'dispatched', 'object':None, 'release_pending':True}
            self._record(journal, record)  # Durable intent BEFORE the physical command.
            try:
                self._command(0x9207, (ONE_SHOT,), data=struct.pack('<H',2), deadline=deadline)
                self._command(0x9207, (ONE_SHOT,), data=struct.pack('<H',1), deadline=deadline)
                record['release_pending'] = False
                self._record(journal, record)
            except CameraError as error:
                error.uncertain = True
                raise
            # Controller journals this reference before it waits/downloads.
            return str(uuid.UUID(capture_id))

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
            if record.get('release_pending'):
                self._command(0x9207, (ONE_SHOT,), data=struct.pack('<H',1), deadline=deadline)
                record['release_pending'] = False
                self._record(journal, record)
            return str(uuid.UUID(capture_id))

    def get_captured_photo(self, reference, deadline, *, quarantine=False):
        with self.lock:
            self._ready()
            journal, saved = self._paths(reference)
            self.recover_capture(reference, deadline,quarantine=quarantine)
            record = json.loads(journal.read_text(encoding='utf-8'))
            if not saved.exists() and reference not in self.transfer_cache:self._restore_rejected(reference,record)
            if saved.exists() or reference in self.transfer_cache:
                data = self.transfer_cache.get(reference) or saved.read_bytes()
                dimensions=check_jpeg(data)
                if len(data) != record['object']['size']:
                    raise CameraError('transfer', 'Sony recovery JPEG size mismatch.', stage='transfer')
                if record.get('sha256') and hashlib.sha256(data).hexdigest() != record['sha256']:
                    raise CameraError('transfer', 'Sony recovery JPEG checksum mismatch.', stage='transfer')
                if not saved.exists():atomic_write(saved,data)
            else:
                while True:
                    count = self._value(self._properties(deadline), FILE_INFO)
                    if record.get('last_buffer_value')!=count:
                        record['last_buffer_value']=count;self._record(journal,record)
                    if count & 0x8000 and count & 0x7fff:break
                    self._wait(deadline)
                info = object_info(self._command(0x1008, (SHOT,), deadline=deadline))
                if info['format'] != 0x3801 or not info['name'].lower().endswith(('.jpg','.jpeg')):
                    raise CameraError('transfer', 'Sony capture buffer is not JPEG. No preview or RAW conversion was substituted.', stage='transfer')
                if record['object'] is not None and record['object'] != info:
                    raise CameraError('recovery_required', 'Camera buffer changed after interrupted transfer; refusing to assign another photo.', stage='transfer')
                record['object'] = info
                self._record(journal, record)
                data = self._command(0x1009, (SHOT,), deadline=deadline, limit=info['size'])
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
                # If local persistence fails after the camera buffer was consumed,
                # retain this one original in memory for retry, without re-firing.
                self.transfer_cache[reference] = data
                atomic_write(saved, data)
            record['jpeg_dimensions']=list(dimensions)
            info=record['object']
            # ZV-E10 virtual ObjectInfo may omit width/height (zero). The JPEG
            # decoder is authoritative in that case; positive values must match.
            if not quarantine and any(info[name]>0 and info[name]!=actual
                                      for name,actual in zip(('width','height'),dimensions)):
                record['validation_error']='JPEG dimensions disagree with nonzero ObjectInfo dimensions.'
                self._record(journal,record)
                raise CameraError('transfer','Sony original JPEG has unexpected dimensions; original bytes retained for recovery.',stage='transfer')
            record.update(status='saved', sha256=hashlib.sha256(data).hexdigest())
            self._record(journal, record)
            self.transfer_cache.pop(reference,None)
            return CapturedPhoto(data, 'image/jpeg', 'camera_original')
