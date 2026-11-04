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
from PIL import Image, UnidentifiedImageError
from .base import CameraCapabilities, CameraError, CapturedPhoto, PreviewFrame
from .sony_wia import MAX_TRANSFER, WindowsWiaTransport
from ..images import atomic_write

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
            if image.format != 'JPEG':raise ValueError()
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
                    raise CameraError('unsupported', 'Expected original Sony ZV-E10; other models, including ZV-E10M2, are not supported.', stage='connect')
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
                                   if json.loads(p.read_text(encoding='utf-8')).get('status') != 'saved'}
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
        with self.lock:
            self._ready()
            if not self.previewing:raise CameraError('not_ready', 'Sony Live View was not requested.', stage='preview')
            deadline = time.monotonic()+min(3, self.timeout)
            if self._value(self._properties(deadline), LIVE_STATUS) != 1:
                raise CameraError('not_ready', 'Camera Live View is temporarily unavailable; check still-photo mode.', stage='preview')
            if not self.preview_limit:
                info = object_info(self._command(0x1008, (LIVE,), deadline=deadline))
                self.preview_limit = min(info['size'], 8*1024*1024)
            wait = self.next_preview - time.monotonic()
            if wait > 0:
                if time.monotonic()+wait >= deadline:raise CameraError('busy', 'Waiting for the next Sony Live View frame.', stage='preview')
                time.sleep(wait)
            self.next_preview = time.monotonic()+0.034  # Sony PTP 2 p.31: <=30 fps.
            data = self._command(0x1009, (LIVE,), deadline=deadline, limit=self.preview_limit)
            reader = Reader(data)
            offset, size = reader.number(4), reader.number(4)
            if offset < 8 or size == 0 or offset+size > len(data):
                raise CameraError('preview', 'Invalid Sony Live View JPEG range.', stage='preview')
            jpeg = data[offset:offset+size]
            check_jpeg(jpeg, preview=True)
            self.sequence += 1
            return PreviewFrame(jpeg, self.sequence, time.time())

    def _paths(self, capture_id):
        capture_id = str(uuid.UUID(capture_id))
        return self.root/(capture_id+'.json'), self.root/(capture_id+'.jpg')

    def _record(self, path, record):
        atomic_write(path, json.dumps(record, sort_keys=True).encode())
        if record.get('status') == 'saved':self.unresolved.discard(path)
        else:self.unresolved.add(path)

    def _pending(self):
        return self.unresolved

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

    def recover_capture(self, capture_id, deadline):
        """Read/reconcile an existing intent. Never sends a shutter-down."""
        with self.lock:
            self._ready()
            journal, _ = self._paths(capture_id)
            if not journal.is_file():raise CameraError('recovery_required', 'No durable Sony capture receipt; cannot safely retry shutter.', uncertain=True)
            record = json.loads(journal.read_text(encoding='utf-8'))
            if record.get('release_pending'):
                self._command(0x9207, (ONE_SHOT,), data=struct.pack('<H',1), deadline=deadline)
                record['release_pending'] = False
                self._record(journal, record)
            return str(uuid.UUID(capture_id))

    def get_captured_photo(self, reference, deadline):
        with self.lock:
            self._ready()
            journal, saved = self._paths(reference)
            self.recover_capture(reference, deadline)
            record = json.loads(journal.read_text(encoding='utf-8'))
            if saved.exists() or reference in self.transfer_cache:
                data = self.transfer_cache.get(reference) or saved.read_bytes()
                check_jpeg(data)
                if len(data) != record['object']['size']:
                    raise CameraError('transfer', 'Sony recovery JPEG size mismatch.', stage='transfer')
                if record.get('sha256') and hashlib.sha256(data).hexdigest() != record['sha256']:
                    raise CameraError('transfer', 'Sony recovery JPEG checksum mismatch.', stage='transfer')
                if not saved.exists():atomic_write(saved,data)
            else:
                while True:
                    count = self._value(self._properties(deadline), FILE_INFO)
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
                if len(data) != info['size'] or check_jpeg(data) != (info['width'], info['height']):
                    raise CameraError('transfer', 'Sony original JPEG is incomplete or has unexpected dimensions.', stage='transfer')
                # If local persistence fails after the camera buffer was consumed,
                # retain this one original in memory for retry, without re-firing.
                self.transfer_cache[reference] = data
                atomic_write(saved, data)
            record.update(status='saved', sha256=hashlib.sha256(data).hexdigest())
            self._record(journal, record)
            self.transfer_cache.pop(reference,None)
            return CapturedPhoto(data, 'image/jpeg', 'camera_original')
