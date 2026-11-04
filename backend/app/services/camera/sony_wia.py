"""Windows' built-in WIA PTP transport, without USB driver replacement.

Independently implemented from Microsoft's IWiaDevMgr/IWiaItemExtras ABI and
vendor-extended-commands documentation. Sony CRC 2.02.00's Windows example
uses this same transport. WIA owns OpenSession, session IDs and transaction IDs.
The apartment lives in one child process: a stalled native call cannot strand
the ASGI worker or cause a second, concurrent camera connection.
"""
import ctypes as C
import multiprocessing as mp
import os
import queue
import struct
import threading
import time
import uuid
from .base import CameraError

MAX_TRANSFER = 64 * 1024 * 1024
IN_HEADER = struct.Struct('<HII5III')
OUT_HEADER = struct.Struct('<HII5I')


def encode_command(opcode, params=(), data=None):
    if not 0 <= opcode <= 0xffff or len(params) > 5:
        raise ValueError('Invalid PTP command')
    # Session/transaction IDs MUST be zero: the Microsoft PTP driver fills them.
    return IN_HEADER.pack(opcode, 0, 0, *params, *([0]*(5-len(params))),
                          len(params), 3 if data is None else 4) + (data or b'')


def decode_response(raw, limit):
    if not OUT_HEADER.size <= len(raw) <= OUT_HEADER.size + limit:
        raise CameraError('protocol', 'Invalid WIA PTP response length.')
    code, _session, _transaction, *_params = OUT_HEADER.unpack_from(raw)
    if code != 0x2001:
        kind = {0x2019:'busy', 0x2003:'disconnected', 0x2005:'unsupported',
                0x200f:'not_ready', 0x2009:'not_ready', 0xa101:'authentication'}.get(code, 'protocol')
        raise CameraError(kind, f'Camera PTP response 0x{code:04X}; check PC Remote, still-photo mode and camera state.')
    return raw[OUT_HEADER.size:]


class GUID(C.Structure):
    _fields_ = [('bytes', C.c_ubyte * 16)]

    @classmethod
    def of(cls, value):
        return cls((C.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))


class _SpecValue(C.Union):
    _fields_ = [('id', C.c_uint32), ('name', C.c_void_p)]


class _Spec(C.Structure):
    _anonymous_ = ('value',)
    _fields_ = [('kind', C.c_uint32), ('value', _SpecValue)]


class _Value(C.Union):
    _fields_ = [('pointer', C.c_void_p), ('number', C.c_uint32),
                ('padding', C.c_byte * (16 if C.sizeof(C.c_void_p) == 8 else 8))]


class _Variant(C.Structure):
    _anonymous_ = ('value',)
    _fields_ = [('vt', C.c_uint16), ('reserved', C.c_uint16 * 3), ('value', _Value)]


def _method(pointer, index, *types):
    address = C.cast(pointer, C.POINTER(C.POINTER(C.c_void_p))).contents[index]
    return C.WINFUNCTYPE(C.c_long, C.c_void_p, *types)(address)


def _check(hr):
    if hr < 0:
        number = hr & 0xffffffff
        kind = {0x80070005:'access', 0x80210006:'busy', 0x80210015:'disconnected',
                0x8007048f:'disconnected'}.get(number, 'usb')
        raise CameraError(kind, f'Windows WIA error 0x{number:08X}. Close Imaging Edge/other camera apps; check USB data cable and PC Remote.', stage='connect')


def _release(pointer):
    if pointer:
        _method(pointer, 2)(pointer)


class _WiaDevice:
    """All methods are invoked in the child's single COM apartment only."""
    def __init__(self):
        self.manager = C.c_void_p()
        self.root = C.c_void_p()
        self.extras = C.c_void_p()
        self.ole = C.WinDLL('ole32')
        self.automation = C.WinDLL('oleaut32')
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [C.c_void_p, C.c_int, C.c_wchar_p]
        self.kernel.CreateMutexW.restype = C.c_void_p
        self.kernel.WaitForSingleObject.argtypes = [C.c_void_p, C.c_uint32]
        self.kernel.ReleaseMutex.argtypes = [C.c_void_p]
        self.kernel.CloseHandle.argtypes = [C.c_void_p]
        self.mutex = None
        self.owns_mutex = False
        self.initialized = False
        self.automation.SysAllocString.argtypes = [C.c_wchar_p]
        self.automation.SysAllocString.restype = C.c_void_p
        self.automation.SysFreeString.argtypes = [C.c_void_p]
        self.ole.PropVariantClear.argtypes = [C.POINTER(_Variant)]

    def _properties(self, storage):
        ids = (2, 3, 4, 5, 7)  # WIA_DIP_DEV_ID/VEND_DESC/DEV_DESC/DEV_TYPE/DEV_NAME
        specs = (_Spec * len(ids))()
        values = (_Variant * len(ids))()
        for spec, prop in zip(specs, ids):
            spec.kind, spec.id = 1, prop  # PRSPEC_PROPID
        try:
            _check(_method(storage, 3, C.c_uint32, C.c_void_p, C.c_void_p)(storage, len(ids), specs, values))
            result = {}
            for prop, value in zip(ids, values):
                if value.vt in (8, 31):  # VT_BSTR, VT_LPWSTR
                    result[prop] = C.wstring_at(value.pointer) if value.pointer else ''
                elif value.vt in (3, 19):
                    result[prop] = value.number
            return result
        finally:
            for value in values:
                self.ole.PropVariantClear(C.byref(value))

    def open(self):
        self.mutex = self.kernel.CreateMutexW(None, False, 'Local\\AmazingRace2026SonyWia')
        if not self.mutex:
            raise CameraError('access', 'Cannot acquire the Sony camera ownership mutex.', stage='connect')
        if self.kernel.WaitForSingleObject(self.mutex, 0) not in (0, 0x80):
            raise CameraError('busy', 'Sony camera is owned by another Photobooth/diagnostic instance.', stage='connect')
        self.owns_mutex = True
        _check(self.ole.CoInitializeEx(None, 2))
        self.initialized = True
        cls = GUID.of('a1f4e726-8cf1-11d1-bf92-0060081ed811')
        iid = GUID.of('5eb2502a-8cf1-11d1-bf92-0060081ed811')
        _check(self.ole.CoCreateInstance(C.byref(cls), None, 4, C.byref(iid), C.byref(self.manager)))
        enum = C.c_void_p()
        try:
            _check(_method(self.manager, 3, C.c_long, C.c_void_p)(self.manager, 0x10, C.byref(enum)))
            candidates = []
            for _ in range(128):
                storage, fetched = C.c_void_p(), C.c_uint32()
                _check(_method(enum, 3, C.c_uint32, C.c_void_p, C.c_void_p)(enum, 1, C.byref(storage), C.byref(fetched)))
                if not fetched.value:
                    break
                try:
                    props = self._properties(storage)
                    descriptor = ' '.join(str(props.get(n, '')) for n in (3,4,7)).upper()
                    # Discovery names are hints only; GetDeviceInfo checks identity.
                    if (props.get(5, 0) & 0xffff) == 2 and ('ZV-E10' in descriptor or 'SONY' in descriptor):
                        candidates.append(props[2])
                finally:
                    _release(storage)
            if not candidates:
                raise CameraError('disconnected', 'No Sony WIA camera. Enable PC Remote/USB, Smartphone Connection Off; use a USB data cable.', stage='connect')
            if len(candidates) != 1:
                raise CameraError('busy', 'Multiple Sony cameras found. Connect only the original ZV-E10.', stage='connect')
            device_id = self.automation.SysAllocString(candidates[0])
            try:
                _check(_method(self.manager, 4, C.c_void_p, C.c_void_p)(self.manager, device_id, C.byref(self.root)))
            finally:
                self.automation.SysFreeString(device_id)
            iid = GUID.of('6291ef2c-36ef-4532-876a-8e132593778d')
            _check(_method(self.root, 0, C.c_void_p, C.c_void_p)(self.root, C.byref(iid), C.byref(self.extras)))
        finally:
            _release(enum)

    def exchange(self, packet, limit):
        incoming = C.create_string_buffer(packet)
        outgoing = C.create_string_buffer(OUT_HEADER.size + limit)
        count = C.c_uint32()
        _check(_method(self.extras, 4, C.c_uint32, C.c_void_p, C.c_uint32,
                       C.c_void_p, C.c_uint32, C.c_void_p)(
                           self.extras, 0x0100, incoming, len(packet), outgoing, len(outgoing), C.byref(count)))
        if count.value > len(outgoing):
            raise CameraError('protocol', 'WIA returned an oversized response.')
        return outgoing.raw[:count.value]

    def close(self):
        # Releasing the WIA root releases its managed PTP session. Do not send
        # a second OpenSession/CloseSession underneath the Windows PTP driver.
        for name in ('extras', 'root', 'manager'):
            pointer = getattr(self, name)
            setattr(self, name, C.c_void_p())
            _release(pointer)
        if self.initialized:
            self.initialized = False
            self.ole.CoUninitialize()
        if self.mutex:
            if self.owns_mutex:self.kernel.ReleaseMutex(self.mutex)
            self.kernel.CloseHandle(self.mutex)
            self.mutex, self.owns_mutex = None, False


def _worker(channel):
    device = None
    try:
        device = _WiaDevice()
        while True:
            request = channel.recv()
            if request[0] == 'close':
                break
            try:
                if request[0] == 'open':
                    device.open()
                    result = None
                else:
                    result = device.exchange(request[1], request[2])
                channel.send(('ok', result))
            except CameraError as error:
                channel.send(('error', error.code, str(error)))
            except Exception:
                channel.send(('error', 'usb', 'Windows WIA operation failed; check camera driver and PC Remote.'))
    except (EOFError, OSError):
        pass
    finally:
        if device is not None:
            device.close()
        channel.close()


class WindowsWiaTransport:
    def __init__(self):
        self.process = self.channel = None
        self.lock = threading.RLock()
        self.responses = queue.Queue(maxsize=1)
        self.reader = None

    @staticmethod
    def _read_replies(channel, responses):
        # Reading a large IPC message can itself block after poll() succeeds.
        # Keep the entire receive off the requesting ASGI thread and include it
        # in the same hard deadline as the native WIA operation.
        try:
            while True:
                responses.put_nowait(channel.recv())
        except (EOFError, OSError):
            try:responses.put_nowait(('error','disconnected','Sony WIA worker disconnected.'))
            except queue.Full:pass
        except queue.Full:
            pass

    def _request(self, request, deadline):
        if time.monotonic() >= deadline:
            raise CameraError('timeout', 'Sony USB operation deadline exceeded.')
        try:
            self.channel.send(request)
            try:
                reply = self.responses.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                self.close(force=True)
                raise CameraError('timeout', 'Sony WIA timed out; connection closed. Shutter requests are never automatically retried.')
        except (OSError, EOFError):
            self.close(force=True)
            raise CameraError('disconnected', 'Sony WIA connection was interrupted.') from None
        if reply[0] == 'error':
            raise CameraError(reply[1], reply[2])
        return reply[1]

    def open(self, deadline):
        if os.name != 'nt':
            raise CameraError('unsupported', 'Sony USB/PTP transport currently requires Windows WIA.', stage='connect')
        with self.lock:
            if self.process:
                return
            context = mp.get_context('spawn')
            self.channel, child = context.Pipe()
            self.process = context.Process(target=_worker, args=(child,), daemon=True, name='photobooth-sony-wia')
            try:
                self.process.start()
                child.close()
                self.responses = queue.Queue(maxsize=1)
                self.reader = threading.Thread(target=self._read_replies,args=(self.channel,self.responses),
                                               daemon=True,name='sony-wia-replies')
                self.reader.start()
                self._request(('open',), deadline)
            except Exception:
                child.close()
                self.close(force=True)
                raise

    def command(self, opcode, params=(), *, data=None, limit=65536, deadline):
        if not 0 <= limit <= MAX_TRANSFER:
            raise ValueError('Sony transfer exceeds buffer limit')
        with self.lock:
            if not self.process or not self.process.is_alive():
                raise CameraError('disconnected', 'Sony WIA is not connected.')
            return decode_response(self._request(('exchange', encode_command(opcode, params, data), limit), deadline), limit)

    def close(self, force=False):
        with self.lock:
            process, channel = self.process, self.channel
            self.process = self.channel = None
            if process is None:
                return
            try:
                if process.is_alive() and not force:
                    try:channel.send(('close',))
                    except (OSError, EOFError):pass
                    process.join(0.5)
                if process.is_alive():
                    process.terminate()  # Only our dedicated WIA child, never another app.
                    process.join(1)
            finally:
                channel.close()
                if self.reader:self.reader.join(0.1)
                self.reader = None
                if not process.is_alive():process.close()
