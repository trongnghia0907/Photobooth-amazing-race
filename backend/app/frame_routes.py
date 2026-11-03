"""Authenticated Host frame management and safe kiosk frame metadata."""
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, StrictBool, StrictFloat, StrictInt
from fastapi.responses import FileResponse

from .printing_routes import host
from .services.images import read_image, atomic_write

admin = APIRouter(prefix='/api/admin/frames', dependencies=[Depends(host)])
booth = APIRouter(prefix='/api/booth/frames')

PRESETS = [
    {'id': 'grid2x3', 'name': 'AMAZING RACE 2026 — Dọc (2 × 3)', 'layout': 'grid2x3', 'slot_count': 6, 'configured': True},
    {'id': 'grid3x2', 'name': 'AMAZING RACE 2026 — Ngang (3 × 2)', 'layout': 'grid3x2', 'slot_count': 6, 'configured': True},
    {'id': 'landscape_4', 'name': 'AMAZING RACE 2026 — 4 ảnh (2 × 2)', 'layout': 'landscape_4', 'slot_count': 4, 'configured': True},
]


class FrameConfig(BaseModel):
    name: str = Field(default='Host custom frame', min_length=1, max_length=160)
    layout: Literal['grid2x3', 'grid3x2', 'landscape_4'] = 'grid2x3'
    slot_count: Literal[4, 6] = 6
    pad_x: StrictFloat = Field(default=6, ge=0, le=30)
    pad_top: StrictFloat = Field(default=7, ge=0, le=30)
    pad_bottom: StrictFloat = Field(default=15, ge=0, le=30)
    gap: StrictFloat = Field(default=3, ge=0, le=30)
    slots: list[list[StrictFloat]] = Field(default_factory=list, max_length=6)
    enabled: StrictBool = True


def _root(request: Request) -> Path:
    return request.app.state.settings.storage_root.resolve()


def _read_config(request: Request):
    with request.app.state.repository.db.connect() as db:
        row = db.execute("SELECT value FROM host_settings WHERE key='frame:custom'").fetchone()
    if not row:
        return None
    try:
        return FrameConfig.model_validate(json.loads(row['value'])).model_dump()
    except (ValueError, TypeError):
        return None


def _write_config(request: Request, config: FrameConfig):
    with request.app.state.repository.db.connect() as db:
        db.execute('INSERT INTO host_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                   ('frame:custom', json.dumps(config.model_dump(), separators=(',', ':'))))


@admin.get('')
def list_frames(request: Request):
    custom = _read_config(request)
    image = _root(request) / 'frames' / 'custom.png'
    items = [*PRESETS]
    if custom:
        items.append({**custom, 'id': 'custom', 'configured': image.is_file(),
                      'image_url': '/api/admin/frames/custom/image' if image.is_file() else None})
    return {'items': items}


@admin.put('/custom')
def save_custom(request: Request, payload: FrameConfig):
    if payload.layout == 'landscape_4' and payload.slot_count != 4:
        raise HTTPException(422, 'Layout 4 ảnh phải dùng slot_count=4')
    if payload.layout != 'landscape_4' and payload.slot_count != 6:
        raise HTTPException(422, 'Layout 6 ảnh phải dùng slot_count=6')
    _write_config(request, payload)
    return {'saved': True, 'frame': payload.model_dump()}


@admin.post('/custom/upload')
async def upload_custom(request: Request, file: UploadFile = File(...)):
    if file.content_type != 'image/png':
        raise HTTPException(415, 'Frame quản trị phải là PNG có alpha')
    image = await read_image(file, request.app.state.settings)
    request.app.state.repository.ensure_disk_space(len(image.data) * 2)
    path = _root(request) / 'frames' / 'custom.png'
    atomic_write(path, image.data)
    config = _read_config(request) or FrameConfig()
    config.name = file.filename or config.name
    _write_config(request, config)
    return {'saved': True, 'width': image.width, 'height': image.height, 'image_url': '/api/admin/frames/custom/image'}


@admin.get('/custom/image')
def custom_image(request: Request):
    path = _root(request) / 'frames' / 'custom.png'
    if not path.is_file() or not _read_config(request):
        raise HTTPException(404, 'Chưa có frame custom được lưu')
    return FileResponse(path, media_type='image/png', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@booth.get('')
def kiosk_frames(request: Request):
    access = request.app.state.booth_access
    if access.enabled:
        access.require(request)
    custom = _read_config(request)
    image = _root(request) / 'frames' / 'custom.png'
    items = [*PRESETS]
    if custom and custom.get('enabled') and image.is_file():
        items.append({k: custom[k] for k in ('name', 'layout', 'slot_count', 'pad_x', 'pad_top', 'pad_bottom', 'gap', 'slots')}
                     | {'id': 'custom', 'configured': True, 'image_url': '/api/booth/frames/custom/image'})
    return {'items': items}


@booth.get('/custom/image')
def kiosk_custom_image(request: Request):
    access = request.app.state.booth_access
    if access.enabled:
        access.require(request)
    config = _read_config(request); path = _root(request) / 'frames' / 'custom.png'
    if not config or not config.get('enabled') or not path.is_file():
        raise HTTPException(404, 'Frame custom chưa được bật')
    return FileResponse(path, media_type='image/png', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
