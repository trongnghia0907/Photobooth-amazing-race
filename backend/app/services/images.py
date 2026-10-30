from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import hashlib
import os
import uuid
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import HTTPException, UploadFile

from ..config import Settings


@dataclass
class ValidatedImage:
    data: bytes
    width: int
    height: int
    sha256: str
    input_hash: str


async def read_image(file: UploadFile, settings: Settings) -> ValidatedImage:
    if file.content_type not in {'image/png', 'image/jpeg', 'image/webp'}:
        raise HTTPException(415, 'Chỉ hỗ trợ PNG, JPEG hoặc WebP')
    data = bytearray()
    while chunk := await file.read(64 * 1024):
        data.extend(chunk)
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(413, 'File ảnh vượt giới hạn dung lượng')
    return validate_image(bytes(data), file.content_type, settings)


def validate_image(data: bytes, content_type: str, settings: Settings) -> ValidatedImage:
    if content_type not in {'image/png', 'image/jpeg', 'image/webp'}:
        raise HTTPException(415, 'Chỉ hỗ trợ PNG, JPEG hoặc WebP')
    if not data or len(data) > settings.max_upload_bytes:
        raise HTTPException(413, 'File ảnh rỗng hoặc vượt giới hạn dung lượng')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as probe:
                if probe.format not in {'PNG', 'JPEG', 'WEBP'}:
                    raise ValueError('Unsupported image format')
                if probe.width * probe.height > settings.max_image_pixels:
                    raise HTTPException(413, 'Ảnh vượt giới hạn số pixel')
                probe.verify()
            with Image.open(BytesIO(data)) as img:
                normalized = ImageOps.exif_transpose(img).convert('RGBA')
                output = BytesIO()
                normalized.save(output, format='PNG')
                payload = output.getvalue()
                return ValidatedImage(payload, normalized.width, normalized.height,
                                      hashlib.sha256(payload).hexdigest(), hashlib.sha256(data).hexdigest())
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, 'File không phải ảnh hợp lệ hoặc đã bị hỏng') from None


def atomic_write(path: Path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'{uuid.uuid4().hex}.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
