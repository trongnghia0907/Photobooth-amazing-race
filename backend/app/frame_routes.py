"""Authenticated Host frame management and safe kiosk frame metadata."""
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, StrictBool, StrictFloat
from fastapi.responses import FileResponse

from .printing_routes import host
from .services.images import read_image, atomic_write

admin = APIRouter(prefix='/api/admin/frames', dependencies=[Depends(host)])
booth = APIRouter(prefix='/api/booth/frames')
FrameLayout = Literal['grid2x3', 'grid3x2', 'landscape_4']
FRAME_LAYOUTS = ('grid2x3', 'landscape_4', 'grid3x2')

PRESETS = [
    {'id': 'grid2x3', 'name': 'AMAZING RACE 2026 — Dọc (2 × 3)', 'layout': 'grid2x3', 'slot_count': 6, 'configured': True},
    {'id': 'grid3x2', 'name': 'AMAZING RACE 2026 — Ngang (3 × 2)', 'layout': 'grid3x2', 'slot_count': 6, 'configured': True},
    {'id': 'landscape_4', 'name': 'AMAZING RACE 2026 — 4 ảnh (2 × 2)', 'layout': 'landscape_4', 'slot_count': 4, 'configured': True},
]


class FrameConfig(BaseModel):
    name: str = Field(default='Host custom frame', min_length=1, max_length=160)
    layout: FrameLayout = 'grid2x3'
    slot_count: Literal[4, 6] = 6
    pad_x: StrictFloat = Field(default=6, ge=0, le=30)
    pad_top: StrictFloat = Field(default=7, ge=0, le=30)
    pad_bottom: StrictFloat = Field(default=15, ge=0, le=30)
    gap: StrictFloat = Field(default=3, ge=0, le=30)
    slots: list[list[StrictFloat]] = Field(default_factory=list, max_length=6)
    enabled: StrictBool = True


def _root(request: Request) -> Path:
    return request.app.state.settings.storage_root.resolve()


def _read_config(request: Request, key: str):
    with request.app.state.repository.db.connect() as db:
        row = db.execute('SELECT value FROM host_settings WHERE key=?', (key,)).fetchone()
    if not row:
        return None
    try:
        return FrameConfig.model_validate(json.loads(row['value'])).model_dump()
    except (ValueError, TypeError):
        return None


def _write_config(request: Request, config: FrameConfig):
    with request.app.state.repository.db.connect() as db:
        db.execute('INSERT INTO host_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                   (f'frame:custom:{config.layout}', json.dumps(config.model_dump(), separators=(',', ':'))))


def _custom_frame(request: Request, layout: FrameLayout):
    config = _read_config(request, f'frame:custom:{layout}')
    path = _root(request) / 'frames' / f'custom-{layout}.png'
    if config is None or not path.is_file():
        legacy = _read_config(request, 'frame:custom')
        if legacy and legacy['layout'] == layout:
            config = config or legacy
            if not path.is_file():
                path = path.with_name('custom.png')
    return config, path


def _default_layout(request: Request) -> FrameLayout:
    legacy = _read_config(request, 'frame:custom')
    return legacy['layout'] if legacy else 'grid2x3'


def _frame_items(request: Request, for_booth: bool):
    items = [*PRESETS]
    prefix = booth.prefix if for_booth else admin.prefix
    for layout in FRAME_LAYOUTS:
        config, path = _custom_frame(request, layout)
        if not config:
            continue
        configured = path.is_file()
        if for_booth and (not config['enabled'] or not configured or layout == 'grid3x2'):
            continue
        items.append({**config, 'id': f'custom-{layout}', 'configured': configured,
                      'image_url': f'{prefix}/custom/image?layout={layout}' if configured else None})
    return items


@admin.get('')
def list_frames(request: Request):
    return {'items': _frame_items(request, for_booth=False)}


@admin.put('/custom')
def save_custom(request: Request, payload: FrameConfig):
    if payload.layout == 'landscape_4' and payload.slot_count != 4:
        raise HTTPException(422, 'Layout 4 ảnh phải dùng slot_count=4')
    if payload.layout != 'landscape_4' and payload.slot_count != 6:
        raise HTTPException(422, 'Layout 6 ảnh phải dùng slot_count=6')
    _write_config(request, payload)
    return {'saved': True, 'frame': payload.model_dump()}


@admin.post('/custom/upload')
async def upload_custom(request: Request, file: UploadFile = File(...), layout: FrameLayout | None = None):
    if file.content_type != 'image/png':
        raise HTTPException(415, 'Frame quản trị phải là PNG có alpha')
    image = await read_image(file, request.app.state.settings)
    request.app.state.repository.ensure_disk_space(len(image.data) * 2)
    layout = layout or _default_layout(request)
    previous, _ = _custom_frame(request, layout)
    config = FrameConfig.model_validate(previous) if previous else FrameConfig(
        layout=layout, slot_count=4 if layout == 'landscape_4' else 6)
    config.name = file.filename[:160] if file.filename else config.name
    config.slots = []
    path = _root(request) / 'frames' / f'custom-{layout}.png'
    atomic_write(path, image.data)
    _write_config(request, config)
    return {'saved': True, 'width': image.width, 'height': image.height,
            'image_url': f'/api/admin/frames/custom/image?layout={layout}'}


@admin.get('/custom/image')
def custom_image(request: Request, layout: FrameLayout | None = None):
    config, path = _custom_frame(request, layout or _default_layout(request))
    if not config or not path.is_file():
        raise HTTPException(404, 'Chưa có frame custom được lưu')
    return FileResponse(path, media_type='image/png', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@booth.get('')
def kiosk_frames(request: Request):
    access = request.app.state.booth_access
    if access.enabled:
        access.require(request)
    return {'items': _frame_items(request, for_booth=True)}


@booth.get('/custom/image')
def kiosk_custom_image(request: Request, layout: FrameLayout | None = None):
    access = request.app.state.booth_access
    if access.enabled:
        access.require(request)
    layout = layout or _default_layout(request)
    config, path = _custom_frame(request, layout)
    if layout == 'grid3x2' or not config or not config['enabled'] or not path.is_file():
        raise HTTPException(404, 'Frame custom chưa được bật')
    return FileResponse(path, media_type='image/png', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
