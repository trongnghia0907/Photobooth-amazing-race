from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, StrictInt
from .routers import Auth, Key
from .printing_routes import host

router = APIRouter(prefix='/api/sessions/{sid}/camera')
admin = APIRouter(prefix='/api/admin/camera',dependencies=[Depends(host)])


@router.get('/status')
def status(request: Request,sid: UUID,owner: Auth):
    return request.app.state.camera.status(str(sid),owner)


@router.post('/connect')
def connect(request: Request,sid: UUID,owner: Auth):
    return request.app.state.camera.connect(str(sid),owner)


@router.post('/disconnect')
def disconnect(request: Request,sid: UUID,owner: Auth):
    return request.app.state.camera.disconnect(str(sid),owner)


@router.post('/live-view/{action}')
def live(request: Request,sid: UUID,owner: Auth,action: Literal['start','stop']):
    return request.app.state.camera.live(str(sid),owner,action=='start')


@router.get('/frame')
def frame(request: Request,sid: UUID,owner: Auth):
    result = request.app.state.camera.frame(str(sid),owner)
    return Response(result.data,media_type='image/jpeg',headers={
        'Cache-Control':'no-store','X-Robots-Tag':'noindex, nofollow','X-Content-Type-Options':'nosniff',
        'X-Frame-Sequence':str(result.sequence),'X-Frame-Time':str(result.captured_at)})


class CaptureRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    slot_index: StrictInt


@router.post('/captures')
def capture(request: Request,sid: UUID,owner: Auth,key: Key,payload: CaptureRequest):
    return request.app.state.camera.capture(str(sid),owner,key,payload.slot_index)


@router.get('/captures/{capture_id}')
def result(request: Request,sid: UUID,capture_id: UUID,owner: Auth):
    return request.app.state.camera.result(str(sid),owner,str(capture_id))


@router.get('/captures/{capture_id}/original')
def original(request: Request,sid: UUID,capture_id: UUID,owner: Auth):
    service = request.app.state.camera
    session=service.authorize(str(sid),owner)
    if session['status']=='completed':raise HTTPException(410,'Ảnh chụp riêng là dữ liệu tạm; phiên đã chốt composite cuối.')
    with service.repo.db.connect() as db:
        row = db.execute('SELECT native_path,native_sha256,mime FROM camera_captures WHERE id=? AND session_id=?',(str(capture_id),str(sid))).fetchone()
    if not row or not row['native_path']:raise HTTPException(404,'Chưa nhận được file gốc')
    path = request.app.state.printing.checked_file(row['native_path'],row['native_sha256'])
    return FileResponse(path,media_type=row['mime'],headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


@admin.get('')
def diagnostics(request: Request):
    return {**request.app.state.camera.status(),
            'adapters':[{'id':'mock','label':'Host Mock — DEMO'},
                        {'id':'uvc_demo','label':'Host webcam frame — DEMO, optional OpenCV'},
                        {'id':'vendor','label':'Vendor SDK — BLOCKED BY HARDWARE'}]}


class Configuration(BaseModel):
    adapter: Literal['mock','uvc_demo','vendor'] | None=None
    guest_enabled: bool | None=None


@admin.put('/config')
def configure(request: Request,payload: Configuration):
    return request.app.state.camera.configure(payload.adapter,payload.guest_enabled)


@admin.post('/disconnect')
def host_disconnect(request: Request):
    return request.app.state.camera.disconnect()


@admin.post('/diagnostic')
def host_diagnostic(request: Request):
    """Host-only capability check; never treats a preview frame as a shutter receipt."""
    # Safe diagnostics are status/capability-only. They never fire a physical
    # shutter or manufacture a result from Live View.
    return request.app.state.camera.diagnose()


class Failure(BaseModel):
    failure: Literal['timeout','capture','transfer','disconnect','stale_preview'] | None=None


@admin.post('/mock-failure')
def fault(request: Request,payload: Failure):
    request.app.state.camera.fault(payload.failure)
    return {'configured':True}
