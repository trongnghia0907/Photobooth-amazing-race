from dataclasses import dataclass, asdict
from typing import Protocol


@dataclass(frozen=True)
class CameraCapabilities:
    adapter: str
    name: str
    demo: bool
    live_view: bool
    capture: bool
    physical_shutter: bool
    original_file: bool
    capture_kind: str
    hardware_verified: bool = False

    def json(self):
        return asdict(self)


@dataclass(frozen=True)
class PreviewFrame:
    data: bytes
    sequence: int
    captured_at: float


@dataclass(frozen=True)
class CapturedPhoto:
    data: bytes
    mime: str
    source: str


class CameraError(Exception):
    def __init__(self, code, message, *, stage='capture', uncertain=False):
        super().__init__(message)
        self.code, self.stage, self.uncertain = code, stage, uncertain


class CameraAdapter(Protocol):
    # Device implementations must honor the deadline and never manufacture a
    # physical-shutter receipt from a preview image. References must be durable.
    def connect(self): ...
    def disconnect(self): ...
    def get_status(self) -> dict: ...
    def get_capabilities(self) -> CameraCapabilities: ...
    def start_live_view(self): ...
    def stop_live_view(self): ...
    def get_preview_frame(self) -> PreviewFrame: ...
    def capture_photo(self, capture_id: str, deadline: float) -> str: ...
    def get_captured_photo(self, reference: str, deadline: float) -> CapturedPhoto: ...
