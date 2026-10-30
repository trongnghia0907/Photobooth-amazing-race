from dataclasses import dataclass, field
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    storage_root: Path
    max_upload_bytes: int = 10 * 1024 * 1024
    max_image_pixels: int = 24_000_000
    public_base_url: str = ''
    app_env: str = 'production'
    printer_mode: str = 'mock'
    max_print_copies: int = 3
    enable_physical_printing: bool = False
    admin_username: str = ''
    admin_password: str = field(default='', repr=False)
    camera_adapter: str = 'mock'
    camera_guest_enabled: bool = False
    camera_device_index: int = 0
    camera_timeout_seconds: float = 15
    camera_lease_seconds: float = 30
    camera_stale_seconds: float = 3
    camera_allow_faults: bool = False
    frontend_dist: Path | None = None
    booth_pairing_key: str = field(default='',repr=False)
    allow_lan_http: bool = False

    def __post_init__(self):
        if not 1 <= self.max_print_copies <= 100:
            raise ValueError('MAX_PRINT_COPIES must be 1..100')
        if self.printer_mode not in ('mock','windows'):
            raise ValueError('PRINTER_MODE must be mock or windows (CUPS is a future adapter)')
        if self.camera_adapter not in ('mock','uvc_demo','vendor'):
            raise ValueError('CAMERA_ADAPTER must be mock, uvc_demo or vendor')
        if not (1 <= self.camera_timeout_seconds <= 120 and 3 <= self.camera_lease_seconds <= 300 and 1 <= self.camera_stale_seconds <= 10):
            raise ValueError('Invalid camera timeouts')
        if self.camera_device_index < 0:
            raise ValueError('CAMERA_DEVICE_INDEX must be >=0')
        if self.frontend_dist and len(self.booth_pairing_key)<16:
            raise ValueError('BOOTH_PAIRING_KEY must have at least 16 characters when serving the kiosk')
        if self.allow_lan_http and self.app_env!='development':
            raise ValueError('ALLOW_LAN_HTTP is development-only')

    @classmethod
    def from_environment(cls):
        default = Path(__file__).resolve().parents[2] / 'runtime'
        return cls(
            Path(os.environ.get('OSA_STORAGE_ROOT', default)).expanduser().resolve(),
            int(os.environ.get('OSA_MAX_UPLOAD_BYTES', 10 * 1024 * 1024)),
            int(os.environ.get('OSA_MAX_IMAGE_PIXELS', 24_000_000)),
            os.environ.get('PUBLIC_BASE_URL', '').strip(),
            os.environ.get('APP_ENV', 'production').strip().lower(),
            os.environ.get('PRINTER_MODE', 'mock').strip().lower(),
            int(os.environ.get('MAX_PRINT_COPIES', '3')),
            os.environ.get('ENABLE_PHYSICAL_PRINTING', '').lower() == 'true',
            os.environ.get('ADMIN_USERNAME', '').strip(),
            os.environ.get('ADMIN_PASSWORD', ''),
            os.environ.get('CAMERA_ADAPTER','mock').strip().lower(),
            os.environ.get('CAMERA_GUEST_ENABLED','').lower() == 'true',
            int(os.environ.get('CAMERA_DEVICE_INDEX','0')),
            float(os.environ.get('CAMERA_TIMEOUT_SECONDS','15')),
            float(os.environ.get('CAMERA_LEASE_SECONDS','30')),
            float(os.environ.get('CAMERA_STALE_SECONDS','3')),
            os.environ.get('CAMERA_ALLOW_FAULTS','').lower() == 'true',
            Path(os.environ['OSA_FRONTEND_DIST']).expanduser().resolve() if os.environ.get('OSA_FRONTEND_DIST') else None,
            os.environ.get('BOOTH_PAIRING_KEY',''),
            os.environ.get('ALLOW_LAN_HTTP','').lower() == 'true',
        )
