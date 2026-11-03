import json
import os
import hashlib
import re
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from .schemas import CreateSession, CompleteSession
from .services.images import read_image

router = APIRouter(prefix='/api')


def token(authorization: Annotated[str | None, Header()] = None):
    if not authorization or not re.fullmatch(r'Bearer [A-Za-z0-9_-]{32,128}', authorization):
        raise HTTPException(401, 'Thiếu session credential hợp lệ')
    return authorization[7:]


def operation_key(idempotency_key: Annotated[str | None, Header()] = None):
    if not idempotency_key or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', idempotency_key):
        raise HTTPException(422, 'Idempotency-Key phải gồm 16–128 ký tự an toàn')
    return idempotency_key


Auth = Annotated[str, Depends(token)]
Key = Annotated[str, Depends(operation_key)]


@router.get('/health')
def health(request: Request):
    with request.app.state.repository.db.connect() as db:
        db.execute('SELECT 1').fetchone()
    return {'status': 'ok', 'phase': 6,'startup_id':os.environ.get('PHOTOBOOTH_STARTUP_ID',''),'operation_mode':request.app.state.settings.operation_mode,
            'runtime_id':hashlib.sha256(str(request.app.state.settings.storage_root.resolve()).encode()).hexdigest(),
            'storage':{'provider':'google_drive' if request.app.state.settings.google_drive_enabled else 'local'},
            'capture_mode': 'physical_camera_required' if request.app.state.settings.operation_mode=='event' else 'demo/webcam_frame/manual_upload/host_adapter',
            'sharing': request.app.state.repository.sharing.configuration()}


@router.post('/sessions')
def create(request: Request, payload: CreateSession, owner: Auth, key: Key):
    if (payload.layout == 'landscape_4') != (payload.slot_count == 4):
        raise HTTPException(422, 'Layout không khớp slot_count')
    result=request.app.state.repository.create(owner, key, payload.model_dump())
    if request.app.state.booth_access.enabled:
        request.app.state.booth_access.bind(result['session_id'],request.state.station_hash)
    return result


@router.get('/sessions/{session_id}')
def get(request: Request, session_id: UUID, owner: Auth):
    return request.app.state.repository.get(str(session_id), owner)


@router.put('/sessions/{session_id}/layout')
def update_layout(request: Request, session_id: UUID, payload: CreateSession, owner: Auth, key: Key):
    if (payload.layout == 'landscape_4') != (payload.slot_count == 4):
        raise HTTPException(422, 'Layout không khớp slot_count')
    # Keep the camera lease/adapter alive; only an unused session's metadata
    # may change. Serialize with capture startup, never with a disconnect.
    camera = request.app.state.camera
    with camera.control:
        if camera.capture_lock.locked():
            raise HTTPException(409, 'Camera đang chụp/truyền ảnh; không thể đổi bố cục.')
        return request.app.state.repository.update_layout(str(session_id), owner, key, payload.model_dump())


@router.post('/sessions/{session_id}/photos')
async def upload_photo(request: Request, session_id: UUID, owner: Auth, key: Key,
                       slot_index: Annotated[int, Form(ge=0, le=5)],
                       source: Annotated[Literal['demo', 'webcam_frame', 'manual_upload'], Form()],
                       file: Annotated[UploadFile, File()]):
    repository = request.app.state.repository
    await run_in_threadpool(repository.get, str(session_id), owner)
    image = await read_image(file, request.app.state.settings)
    return await run_in_threadpool(repository.upload_photo, str(session_id), owner, key, slot_index, source, image)


@router.delete('/sessions/{session_id}/photos')
def reset(request: Request, session_id: UUID, owner: Auth, key: Key):
    return request.app.state.repository.delete_photos(str(session_id), owner, key)


@router.delete('/sessions/{session_id}/photos/{slot_index}')
def delete(request: Request, session_id: UUID, slot_index: int, owner: Auth, key: Key):
    return request.app.state.repository.delete_photos(str(session_id), owner, key, slot_index)


@router.put('/sessions/{session_id}/composite')
async def upload_composite(request: Request, session_id: UUID, owner: Auth, key: Key,
                           shots_revision: Annotated[int, Form(ge=0)],
                           file: Annotated[UploadFile, File()],
                           editor_json: Annotated[str, Form(max_length=32000)] = '{}'):
    repository = request.app.state.repository
    await run_in_threadpool(repository.get, str(session_id), owner)
    try:
        editor = json.loads(editor_json)
        if not isinstance(editor, dict):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, 'editor_json phải là JSON object') from None
    image = await read_image(file, request.app.state.settings)
    return await run_in_threadpool(repository.upload_composite, str(session_id), owner, key, shots_revision, editor, image)


@router.post('/sessions/{session_id}/complete')
def complete(request: Request, session_id: UUID, payload: CompleteSession, owner: Auth, key: Key):
    return request.app.state.repository.complete(str(session_id), owner, key, payload.composite_id)


@router.post('/sessions/{session_id}/finalize')
def finalize(request: Request, session_id: UUID, payload: CompleteSession, owner: Auth, key: Key):
    return request.app.state.repository.sharing.finalize(str(session_id), owner, key, payload.composite_id)


@router.get('/sessions/{session_id}/public-status')
def public_status(request:Request,session_id:UUID,owner:Auth):
    return request.app.state.repository.sharing.verify_public(str(session_id),owner)


@router.get('/sessions/{session_id}/{kind}/{image_id}/image')
def image(request: Request, session_id: UUID, kind: Literal['photos', 'composites'], image_id: UUID, owner: Auth):
    path = request.app.state.repository.image_path(str(session_id), owner, kind, str(image_id))
    return FileResponse(path, media_type='image/png', headers={
        'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow', 'X-Content-Type-Options': 'nosniff',
    })
