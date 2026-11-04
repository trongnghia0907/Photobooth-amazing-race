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
    operation_mode: str = 'development'
    allow_mock_hardware: bool = False
    printer_name: str = ''
    camera_model: str = ''
    guest_idle_seconds: int = 180
    gallery_poll_seconds: int = 5
    min_free_space_mb: int = 64
    log_level: str = 'info'
    log_directory: Path | None = None
    cups_lp: str = 'lp'
    cups_lpstat: str = 'lpstat'
    google_drive_enabled: bool = False
    google_drive_folder_id: str = '1ixmork-KFJ8xdtQCFJIpUTQm-SnJqeez'
    google_oauth_client_file: Path | None = None
    event_gallery_auto_publish: bool = True
    public_gallery_enabled: bool = False

    @property
    def demo_hardware_allowed(self):
        return self.operation_mode == 'development' or (self.operation_mode == 'rehearsal' and self.allow_mock_hardware)

    def __post_init__(self):
        if self.google_drive_folder_id!='1ixmork-KFJ8xdtQCFJIpUTQm-SnJqeez':
            raise ValueError('Google Drive destination must be the approved Photobooth folder')
        if not 1 <= self.max_print_copies <= 100:
            raise ValueError('MAX_PRINT_COPIES must be 1..100')
        if self.app_env not in ('development','production'):
            raise ValueError('APP_ENV must be development or production')
        if self.operation_mode not in ('development','rehearsal','event'):
            raise ValueError('OPERATION_MODE must be development, rehearsal or event')
        if self.operation_mode == 'event' and (self.app_env != 'production' or self.allow_mock_hardware):
            raise ValueError('Event mode requires APP_ENV=production and ALLOW_MOCK_HARDWARE=false')
        if self.operation_mode=='event' and self.camera_allow_faults:
            raise ValueError('Event mode forbids CAMERA_ALLOW_FAULTS')
        if self.operation_mode == 'rehearsal' and not self.allow_mock_hardware:
            raise ValueError('Rehearsal requires explicit ALLOW_MOCK_HARDWARE=true')
        if self.printer_mode not in ('mock','windows','cups'):
            raise ValueError('PRINTER_MODE must be mock, windows or cups')
        if not (0 <= self.guest_idle_seconds <= 86400 and 3 <= self.gallery_poll_seconds <= 60 and 0 <= self.min_free_space_mb <= 1048576):
            raise ValueError('Invalid guest idle, gallery polling or disk reserve configuration')
        if self.log_level not in ('debug','info','warning','error','critical'):
            raise ValueError('Invalid LOG_LEVEL')
        if self.camera_adapter not in ('mock','uvc_demo','vendor','sony_zve10'):
            raise ValueError('CAMERA_ADAPTER must be mock, uvc_demo, vendor or sony_zve10')
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
        app_env=os.environ.get('APP_ENV','production').strip().lower()
        mode=os.environ.get('OPERATION_MODE','event' if app_env=='production' else 'development').strip().lower()
        if app_env=='production' and mode=='development':raise ValueError('Production requires event mode, or explicit rehearsal with mock permission')
        def flag(name,default='false'):
            value=os.environ.get(name,default).strip().lower()
            if value not in ('true','false'):raise ValueError(f'{name} must be true or false')
            return value=='true'
        return cls(
            Path(os.environ.get('OSA_STORAGE_ROOT', default)).expanduser().resolve(),
            int(os.environ.get('OSA_MAX_UPLOAD_BYTES', 10 * 1024 * 1024)),
            int(os.environ.get('OSA_MAX_IMAGE_PIXELS', 24_000_000)),
            os.environ.get('PUBLIC_BASE_URL', '').strip(),
            os.environ.get('APP_ENV', 'production').strip().lower(),
            os.environ.get('PRINTER_MODE', 'mock').strip().lower(),
            int(os.environ.get('MAX_PRINT_COPIES', '3')),
            flag('ENABLE_PHYSICAL_PRINTING'),
            os.environ.get('ADMIN_USERNAME', '').strip(),
            os.environ.get('ADMIN_PASSWORD', ''),
            os.environ.get('CAMERA_ADAPTER','mock').strip().lower(),
            flag('CAMERA_GUEST_ENABLED'),
            int(os.environ.get('CAMERA_DEVICE_INDEX','0')),
            float(os.environ.get('CAMERA_TIMEOUT_SECONDS','15')),
            float(os.environ.get('CAMERA_LEASE_SECONDS','30')),
            float(os.environ.get('CAMERA_STALE_SECONDS','3')),
            flag('CAMERA_ALLOW_FAULTS'),
            Path(os.environ['OSA_FRONTEND_DIST']).expanduser().resolve() if os.environ.get('OSA_FRONTEND_DIST') else None,
            os.environ.get('BOOTH_PAIRING_KEY',''),
            flag('ALLOW_LAN_HTTP'),
            operation_mode=mode,
            allow_mock_hardware=flag('ALLOW_MOCK_HARDWARE'),
            printer_name=os.environ.get('PRINTER_NAME','').strip(),
            camera_model=os.environ.get('CAMERA_MODEL','').strip(),
            guest_idle_seconds=int(os.environ.get('GUEST_SESSION_IDLE_SECONDS','180')),
            gallery_poll_seconds=int(os.environ.get('EVENT_GALLERY_POLL_SECONDS','5')),
            min_free_space_mb=int(os.environ.get('MIN_FREE_SPACE_MB','64')),
            log_level=os.environ.get('LOG_LEVEL','info').strip().lower(),
            log_directory=Path(os.environ['OSA_LOG_DIRECTORY']).expanduser().resolve() if os.environ.get('OSA_LOG_DIRECTORY') else None,
            cups_lp=os.environ.get('CUPS_LP_COMMAND','lp'),
            cups_lpstat=os.environ.get('CUPS_LPSTAT_COMMAND','lpstat'),
            google_drive_enabled=flag('GOOGLE_DRIVE_ENABLED'),
            event_gallery_auto_publish=flag('EVENT_GALLERY_AUTO_PUBLISH','true'),
            public_gallery_enabled=flag('PUBLIC_GALLERY_ENABLED'),
            google_drive_folder_id=os.environ.get('GOOGLE_DRIVE_FOLDER_ID','1ixmork-KFJ8xdtQCFJIpUTQm-SnJqeez'),
            google_oauth_client_file=Path(os.environ['GOOGLE_OAUTH_CLIENT_FILE']).expanduser().resolve() if os.environ.get('GOOGLE_OAUTH_CLIENT_FILE') else None,
        )
