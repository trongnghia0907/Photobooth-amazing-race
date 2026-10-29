from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    storage_root: Path
    max_upload_bytes: int = 10 * 1024 * 1024
    max_image_pixels: int = 24_000_000

    @classmethod
    def from_environment(cls):
        default = Path(__file__).resolve().parents[2] / 'runtime'
        return cls(
            Path(os.environ.get('OSA_STORAGE_ROOT', default)).expanduser().resolve(),
            int(os.environ.get('OSA_MAX_UPLOAD_BYTES', 10 * 1024 * 1024)),
            int(os.environ.get('OSA_MAX_IMAGE_PIXELS', 24_000_000)),
        )
