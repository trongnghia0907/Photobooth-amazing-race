"""Original ZV-E10 adapter; real Windows WIA/PTP driver by default.

Explicit driver injection remains available for contract tests. Neither protocol
tests nor an implemented transport constitute physical hardware verification.
"""
from dataclasses import replace
from io import BytesIO
import time
import uuid
from PIL import Image, UnidentifiedImageError
from .base import CameraCapabilities, CameraError, CapturedPhoto
from .sony_ptp import SonyPtpDriver

_DEFAULT_DRIVER = object()


class SonyZvE10CameraAdapter:
    def __init__(self, driver=_DEFAULT_DRIVER, *, storage_root=None, timeout=15):
        self.driver=SonyPtpDriver(storage_root,timeout) if driver is _DEFAULT_DRIVER else driver
        self.connected=False

    def get_capabilities(self):
        if self.driver is None:
            return CameraCapabilities('sony_zve10','Sony ZV-E10 — Camera Remote Command driver missing',
                                      False,False,False,False,False,'unsupported')
        cap=self.driver.get_capabilities()
        if cap.demo or not (cap.capture and cap.physical_shutter and cap.original_file) or cap.capture_kind!='camera_original':
            raise CameraError('unsupported','Sony requires a real shutter/original-JPEG driver; DEMO/preview substitution is forbidden.',stage='connect')
        return replace(cap,adapter='sony_zve10',name='Sony ZV-E10 — Windows WIA/PTP, hardware NOT VERIFIED',hardware_verified=False)

    def get_status(self):
        if self.driver is None:
            return {'connected':False,'previewing':False,'model':'ZV-E10',
                    'integration_available':False,'hardware_verified':False,
                    'blocker':'Obtain Sony Camera Remote Command reference/example code and verify ZV-E10 commands; no USB/PTP driver is implemented.'}
        state=self.driver.get_status()
        return {'connected':bool(self.connected and state.get('connected')),
                'previewing':bool(self.connected and state.get('previewing')),
                'model':state.get('model'),'integration_available':True,'hardware_verified':False}

    def _driver(self, stage):
        if self.driver is None:
            raise CameraError('unsupported','Sony ZV-E10: Camera Remote Command reference/sample driver is missing. No shutter or preview command was sent.',stage=stage)
        return self.driver

    def _ready(self, stage):
        driver=self._driver(stage)
        if not self.get_status()['connected']:
            raise CameraError('disconnected','Sony ZV-E10 is not connected.',stage=stage)
        return driver

    @staticmethod
    def _deadline(deadline, stage, uncertain=False):
        if time.monotonic()>deadline:
            raise CameraError('timeout','Sony '+stage+' deadline exceeded.',stage=stage,uncertain=uncertain)

    def connect(self):
        driver=self._driver('connect')
        if self.get_status()['connected']:return
        self.get_capabilities()
        try:
            driver.connect()
            state=driver.get_status()
            if state.get('model')!='ZV-E10':
                raise CameraError('unsupported','Expected original Sony ZV-E10; ZV-E10 II/other models are not accepted by this adapter.',stage='connect')
            if not state.get('connected'):
                raise CameraError('disconnected','Sony ZV-E10 was not found or could not connect.',stage='connect')
            self.connected=True
        except Exception as error:
            try:self.disconnect()
            except Exception as cleanup_error:raise error from cleanup_error
            raise

    def disconnect(self):
        try:
            if self.driver is not None:
                try:self.driver.stop_live_view()
                finally:self.driver.disconnect()
        finally:self.connected=False

    def start_live_view(self):self._ready('preview').start_live_view()
    def stop_live_view(self):
        if self.driver is not None:self.driver.stop_live_view()

    def get_preview_frame(self):
        # A temporary busy/preview error must not disconnect the USB session.
        return self._ready('preview').get_preview_frame()

    def capture_photo(self, capture_id, deadline):
        uuid.UUID(capture_id)
        driver=self._ready('capture');self._deadline(deadline,'capture')
        try:reference=driver.capture_photo(capture_id,deadline)
        except TimeoutError:
            raise CameraError('timeout','Sony shutter outcome is unknown; do not trigger another shutter automatically.',uncertain=True) from None
        except CameraError as error:
            if error.code in ('timeout','disconnect','disconnected'):error.uncertain=True
            raise
        self._deadline(deadline,'capture',uncertain=True)
        if not isinstance(reference,str) or not reference:
            raise CameraError('capture','Sony did not return a durable capture reference.',uncertain=True)
        return reference

    def recover_capture(self, capture_id, deadline):
        driver=self._ready('transfer')
        self._deadline(deadline,'transfer')
        recovery=getattr(driver,'recover_capture',None)
        if recovery is None:
            raise CameraError('recovery_required','This driver cannot reconcile an uncertain capture; no new shutter was sent.',stage='transfer',uncertain=True)
        return recovery(capture_id,deadline)

    def capture_persisted(self, capture_id):
        if isinstance(self.driver,SonyPtpDriver):self.driver.capture_persisted(capture_id)

    def get_captured_photo(self, reference, deadline):
        driver=self._ready('transfer');self._deadline(deadline,'transfer')
        try:photo=driver.get_captured_photo(reference,deadline)
        except TimeoutError:
            raise CameraError('timeout','Sony JPEG transfer timed out; retry the same capture reference.',stage='transfer') from None
        except CameraError as error:
            # A native transport defaults to stage=capture. At this boundary a
            # shutter receipt already exists: the UI must retry the same transfer.
            error.stage='transfer'
            raise
        self._deadline(deadline,'transfer')
        if (not isinstance(photo,CapturedPhoto) or not isinstance(photo.data,bytes) or not photo.data
                or photo.mime!='image/jpeg' or photo.source!='camera_original'):
            raise CameraError('transfer','Sony requires the original camera JPEG, never a preview/webcam image.',stage='transfer')
        try:
            with Image.open(BytesIO(photo.data)) as image:
                if image.format!='JPEG':raise ValueError('Not JPEG')
                # JPEG verify() alone accepts truncated pixel data. Decode it,
                # but retain the original bytes/EXIF rather than re-encoding.
                image.load()
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):
            raise CameraError('transfer','Sony returned an invalid JPEG; the photo slot was not replaced.',stage='transfer') from None
        self._deadline(deadline,'transfer')
        return photo  # unchanged original bytes; persistence belongs to CameraController
