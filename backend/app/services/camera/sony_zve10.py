"""Original ZV-E10 boundary, NOT a Sony PTP implementation.

Sony lists ZV-E10 under Camera Remote Command, not Camera Remote SDK.
https://support.d-imaging.sony.co.jp/app/cameraremotecommand/en/index.html
The licensed command reference/sample is not present in this repository. Real
operations fail closed until a driver based on its per-model command matrix is
implemented. `driver` is dependency injection of our existing CameraAdapter
contract for fake tests/future integration, never a guessed Sony API or opcode.
Native I/O deadlines must be enforced by that future driver; this boundary only
checks deadlines before/after calls and cannot cancel a hung USB driver.
"""
from dataclasses import replace
from io import BytesIO
import time
import uuid
from PIL import Image, UnidentifiedImageError
from .base import CameraCapabilities, CameraError


class SonyZvE10CameraAdapter:
    def __init__(self, driver=None):
        self.driver=driver
        self.connected=False

    def get_capabilities(self):
        if self.driver is None:
            return CameraCapabilities('sony_zve10','Sony ZV-E10 — Camera Remote Command driver missing',
                                      False,False,False,False,False,'unsupported')
        cap=self.driver.get_capabilities()
        if cap.demo or not (cap.capture and cap.physical_shutter and cap.original_file) or cap.capture_kind!='camera_original':
            raise CameraError('unsupported','Sony requires a real shutter/original-JPEG driver; DEMO/preview substitution is forbidden.',stage='connect')
        return replace(cap,adapter='sony_zve10',name='Sony ZV-E10 — PTP boundary, hardware NOT VERIFIED',hardware_verified=False)

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
        except Exception:
            self.disconnect();raise

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

    def get_captured_photo(self, reference, deadline):
        driver=self._ready('transfer');self._deadline(deadline,'transfer')
        try:photo=driver.get_captured_photo(reference,deadline)
        except TimeoutError:
            raise CameraError('timeout','Sony JPEG transfer timed out; retry the same capture reference.',stage='transfer') from None
        self._deadline(deadline,'transfer')
        if photo.mime!='image/jpeg' or photo.source!='camera_original':
            raise CameraError('transfer','Sony requires the original camera JPEG, never a preview/webcam image.',stage='transfer')
        try:
            with Image.open(BytesIO(photo.data)) as image:
                if image.format!='JPEG':raise ValueError('Not JPEG')
                image.verify()
        except (UnidentifiedImageError,OSError,ValueError):
            raise CameraError('transfer','Sony returned an invalid JPEG; the photo slot was not replaced.',stage='transfer') from None
        return photo  # unchanged original bytes; persistence belongs to CameraController
