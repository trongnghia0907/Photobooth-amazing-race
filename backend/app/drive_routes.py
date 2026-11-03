"""Host-only Drive diagnostics; never returns secrets/file IDs."""
from fastapi import APIRouter,Depends,Request,HTTPException
from .printing_routes import host
from .services.drive_client import DriveError
from uuid import UUID

router=APIRouter(prefix='/api/admin/storage/drive',dependencies=[Depends(host)])

@router.get('')
def status(request:Request):
    return request.app.state.repository.drive.status()

@router.post('/check')
def check(request:Request):
    service=request.app.state.repository.drive
    try:service.check()
    except DriveError as error:raise HTTPException(409,str(error)) from None
    return service.status()

@router.post('/retry')
def retry(request:Request):
    service=request.app.state.repository.drive
    service.retry()
    return service.status()

@router.post('/connect')
def connect(request:Request):
    return {'instruction':'Trên laptop Host: chạy backend/.venv/Scripts/python.exe scripts/connect_google_drive.py. OAuth chỉ dùng drive.file; không tự mở rộng quyền hoặc sửa permission.'}

@router.post('/test')
def test_upload(request:Request):
    try:return request.app.state.repository.drive.test_upload()
    except DriveError as error:raise HTTPException(409,str(error)) from None

@router.post('/cache/{composite_id}/evict')
def evict(request:Request,composite_id:UUID):
    try:request.app.state.repository.drive.evict(str(composite_id))
    except DriveError as error:raise HTTPException(409,str(error)) from None
    return {'cache_removed':True}
