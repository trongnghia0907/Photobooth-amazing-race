from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, StrictInt
from .routers import Auth, Key
from .services.admin_auth import COOKIE, COOKIE_PATH

router = APIRouter(prefix='/api')
admin = APIRouter(prefix='/api/admin')


class PrintRequest(BaseModel):
    final_id: UUID
    copies: StrictInt = 1


@router.get('/print-config')
def print_config(request: Request):
    return request.app.state.printing.config()


@router.post('/sessions/{sid}/print-jobs')
def enqueue(request: Request, sid: UUID, payload: PrintRequest, owner: Auth, key: Key):
    return request.app.state.printing.enqueue(str(sid),str(payload.final_id),payload.copies,key,owner)


@router.get('/sessions/{sid}/print-jobs/{job_id}')
def job(request: Request, sid: UUID, job_id: UUID, owner: Auth):
    return request.app.state.printing.get(str(job_id),str(sid),owner)


def host(request: Request):
    return request.app.state.admin_auth.require(request,request.method not in ('GET','HEAD'))


class Login(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=1000)


@admin.post('/login')
def login(request: Request, payload: Login, response: Response):
    if request.headers.get('X-OSA-Login') != '1':
        raise HTTPException(403,'Thiếu login header')
    auth = request.app.state.admin_auth
    token = auth.login(payload.username,payload.password,request.client.host)
    response.set_cookie(COOKIE,token,httponly=True,samesite='strict',secure=auth.settings.app_env != 'development',
                        path=COOKIE_PATH,max_age=8*3600)
    response.headers['Cache-Control'] = 'no-store'
    return {'csrf_token':auth.csrf(token)}


@admin.get('/me',dependencies=[Depends(host)])
def me(request: Request):
    auth = request.app.state.admin_auth
    return {'username':auth.settings.admin_username,'csrf_token':auth.csrf(request.cookies[COOKIE])}


@admin.post('/logout',dependencies=[Depends(host)])
def logout(request: Request,response: Response):
    request.app.state.admin_auth.logout(request.cookies[COOKIE])
    response.delete_cookie(COOKIE,path=COOKIE_PATH)
    return {'logged_out':True}


@admin.get('/status',dependencies=[Depends(host)])
def status(request: Request):
    with request.app.state.repository.db.connect() as db:
        counts = {name:db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                  for name,table in [('sessions','sessions'),('photos','session_finals'),('composites','session_finals')]}
        for state in ('queued','processing','failed'):
            counts[state] = db.execute('SELECT COUNT(*) FROM print_jobs WHERE status=?',(state,)).fetchone()[0]
    return {'backend':'online',**counts,'printer':request.app.state.printing.config()}


@admin.get('/sessions',dependencies=[Depends(host)])
def sessions(request: Request,limit: int=20,offset: int=0,include_working:bool=False):
    limit,offset = max(1,min(100,limit)),max(0,offset)
    with request.app.state.repository.db.connect() as db:
        predicate='' if include_working else 'WHERE f.session_id IS NOT NULL'
        rows = db.execute(f'''SELECT s.id,s.status,s.layout,s.slot_count,s.created_at,s.updated_at,f.composite_id,
            COALESCE(e.approved,0) AS display_approved
            FROM sessions s LEFT JOIN session_finals f ON f.session_id=s.id
            LEFT JOIN event_display_photos e ON e.session_id=s.id {predicate} ORDER BY s.created_at DESC LIMIT ? OFFSET ?''',(limit,offset)).fetchall()
        return {'items':[dict(r) for r in rows],'limit':limit,'offset':offset,
                'total':db.execute('SELECT COUNT(*) FROM sessions' if include_working else 'SELECT COUNT(*) FROM session_finals').fetchone()[0]}


@admin.get('/sessions/{sid}',dependencies=[Depends(host)])
def detail(request: Request,sid: UUID):
    repo = request.app.state.repository
    with repo.db.connect() as db:
        row = db.execute('SELECT id,status,layout,slot_count,created_at FROM sessions WHERE id=?',(str(sid),)).fetchone()
        if not row:
            raise HTTPException(404,'Không tìm thấy phiên')
        composites = []
        event=db.execute('SELECT approved,approval_basis FROM event_display_photos WHERE session_id=?',(str(sid),)).fetchone()
        for c in db.execute('SELECT c.* FROM composites c JOIN session_finals f ON f.composite_id=c.id WHERE f.session_id=?',(str(sid),)).fetchall():
            share = db.execute('SELECT id FROM shares WHERE composite_id=?',(c['id'],)).fetchone()
            ready = db.execute('SELECT * FROM print_ready WHERE final_id=?',(share['id'],)).fetchone() if share else None
            composites.append({**repo.composite_metadata(c),
                'image_url':f"/api/admin/sessions/{sid}/images/composites/{c['id']}",
                'final_id':share['id'] if share else None,
                'print_ready_url':f"/api/admin/sessions/{sid}/images/print_ready/{share['id']}" if ready else None})
        return {**dict(row),'composites':composites,'event_display':dict(event) if event else {'approved':False,'approval_basis':None}}


@admin.get('/sessions/{sid}/images/{kind}/{image_id}',dependencies=[Depends(host)])
def host_image(request: Request,sid: UUID,kind: Literal['composites','print_ready','photos'],image_id: UUID,download: bool=False):
    repo = request.app.state.repository
    with repo.db.connect() as db:
        if kind=='photos':raise HTTPException(404,'Host Dashboard chỉ cung cấp composite cuối và bản in của phiên.')
        if kind == 'print_ready':
            row = db.execute('SELECT p.path FROM print_ready p JOIN shares s ON s.id=p.final_id JOIN session_finals f ON f.composite_id=s.composite_id WHERE p.final_id=? AND f.session_id=?',(str(image_id),str(sid))).fetchone()
        else:
            row = db.execute('SELECT c.path FROM composites c JOIN session_finals f ON f.composite_id=c.id WHERE c.id=? AND f.session_id=?',(str(image_id),str(sid))).fetchone()
        if not row:
            raise HTTPException(404,'Không tìm thấy ảnh')
        root = repo.settings.storage_root.resolve()
        path = (root/row['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(404,'Không tìm thấy ảnh')
    return FileResponse(path,media_type='image/png',filename=f'osa-{image_id}.png' if download else None,
                        headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


@admin.get('/print-jobs',dependencies=[Depends(host)])
def jobs(request: Request,limit: int=50,offset: int=0):
    with request.app.state.repository.db.connect() as db:
        return {'items':[request.app.state.printing.metadata(r) for r in db.execute(
            'SELECT * FROM print_jobs ORDER BY seq DESC LIMIT ? OFFSET ?',(max(1,min(100,limit)),max(0,offset)))]}


class HostPrint(PrintRequest):
    session_id: UUID


@admin.post('/print-jobs',dependencies=[Depends(host)])
def reprint(request: Request,payload: HostPrint,key: Key):
    return request.app.state.printing.enqueue(str(payload.session_id),str(payload.final_id),payload.copies,key)


class Retry(BaseModel):
    acknowledge_uncertain: bool=False


@admin.post('/print-jobs/{job_id}/retry',dependencies=[Depends(host)])
def retry(request: Request,job_id: UUID,payload: Retry,key: Key):
    service = request.app.state.printing
    old = service.get(str(job_id))
    return service.enqueue(old['session_id'],old['final_id'],old['copies'],key,retry_of=old['id'],acknowledge=payload.acknowledge_uncertain)


@admin.post('/print-jobs/{job_id}/cancel',dependencies=[Depends(host)])
def cancel(request: Request,job_id: UUID):
    with request.app.state.repository.db.connect() as db:
        result = db.execute("UPDATE print_jobs SET status='cancelled',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=? AND status='queued'",(str(job_id),))
        if result.rowcount != 1:
            raise HTTPException(409,'Chỉ hủy job đang queued')
    return request.app.state.printing.get(str(job_id))


@admin.get('/printers',dependencies=[Depends(host)])
def printers(request: Request):
    service = request.app.state.printing
    with service.repo.db.connect() as db:
        return {'items':service.printers(),'selected':service.selected(db),**service.config()}


class Selection(BaseModel):
    printer_id: str = Field(max_length=500)


@admin.put('/printers/selected',dependencies=[Depends(host)])
def select_printer(request: Request,payload: Selection):
    service = request.app.state.printing
    if payload.printer_id not in [p['id'] for p in service.printers()]:
        raise HTTPException(422,'Máy in không có trong danh sách driver')
    with service.repo.db.connect() as db:
        db.execute('INSERT INTO host_settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                   ('printer:'+service.settings.printer_mode,payload.printer_id))
    return {'selected':payload.printer_id}
