"""Restricted event projection: explicit Host consent, independent display access.

Only the private host app mounts these routes. Never mount on public_main.
No share tokens, storage paths, source captures or download endpoints in this API.
"""
import hashlib
import hmac
import secrets
import time
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, StrictBool
from .booth_access import RateLimit
from .printing_routes import host

COOKIE='osa_event_display'
PREFIX='/event-display'
UI=Path(__file__).parent/'event_ui'
HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
         'Referrer-Policy':'no-referrer','X-Robots-Tag':'noindex, nofollow',
         'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"}
router=APIRouter(prefix=PREFIX)
admin=APIRouter(prefix='/api/admin/event-display',dependencies=[Depends(host)])
booth_gallery=APIRouter(prefix='/api/booth/recent-photos')


def digest(value):return hashlib.sha256(value.encode()).hexdigest()


class EventDisplay:
    def __init__(self,repo):self.repo=repo;self.limiter=RateLimit()

    def access(self,enabled):
        code=secrets.token_urlsafe(24) if enabled else None
        with self.repo.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE event_display_config SET access_hash=? WHERE id=1',(digest(code) if code else None,))
            db.execute('DELETE FROM event_display_sessions')
            db.commit()
        return code

    def unlock(self,code,ip):
        self.limiter.check(('display-unlock',ip),5)
        stamp=time.time()
        with self.repo.db.connect() as db:
            # Serialize against code rotation/revocation, including new session insertion.
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT access_hash FROM event_display_config WHERE id=1').fetchone()
            if not row['access_hash'] or not hmac.compare_digest(digest(code),row['access_hash']):
                raise HTTPException(401,'Mã màn hình không đúng hoặc màn hình sự kiện chưa được bật.')
            token=secrets.token_urlsafe(32)
            db.execute('DELETE FROM event_display_sessions WHERE expires_at<?',(stamp,))
            db.execute('INSERT INTO event_display_sessions VALUES(?,?)',(digest(token),stamp+12*3600))
            db.commit()
        return token

    def require(self,request):
        token=request.cookies.get(COOKIE,'')
        with self.repo.db.connect() as db:
            row=db.execute('''SELECT 1 FROM event_display_sessions s,event_display_config c
                WHERE c.id=1 AND c.access_hash IS NOT NULL AND s.token_hash=? AND s.expires_at>?''',(digest(token),time.time())).fetchone()
        if not row:raise HTTPException(401,'Nhập mã màn hình sự kiện để tiếp tục trình chiếu.')

    def file(self,row,verify=False):
        if row['path']!=f"composites/{row['session_id']}/{row['id']}.png":
            raise HTTPException(404,'Composite không còn sẵn sàng để trình chiếu.')
        root=self.repo.settings.storage_root.resolve();candidate=root/row['path'];path=candidate.resolve()
        if not path.is_file():self.repo.drive.local(row['id'])
        if path!=candidate or not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(404,'Composite không còn sẵn sàng để trình chiếu.')
        if verify and hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise HTTPException(409,'Composite không toàn vẹn; chưa thể duyệt trình chiếu.')
        return path

    def approve(self,sid,payload):
        if payload.approved and (not payload.consent_confirmed or not payload.approval_basis):
            raise HTTPException(422,'Cần chọn cơ sở đồng ý/ủy quyền và xác nhận trước khi duyệt ảnh.')
        with self.repo.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('''SELECT c.* FROM session_finals f JOIN composites c ON c.id=f.composite_id
                JOIN sessions s ON s.id=f.session_id WHERE f.session_id=? AND s.status='completed'
                AND s.composite_id=c.id AND c.session_id=s.id''',(sid,)).fetchone()
            if not row:raise HTTPException(409,'Chỉ được duyệt composite cuối đã lưu và chốt thành công.')
            if payload.approved:
                self.file(row,verify=True)
                existing=db.execute('SELECT approved,approval_basis FROM event_display_photos WHERE session_id=?',(sid,)).fetchone()
                if existing and existing['approved'] and existing['approval_basis']==payload.approval_basis:
                    return {'approved':True}
                db.execute('''INSERT INTO event_display_photos VALUES(?,?,?,?,?,?,?,NULL)
                    ON CONFLICT(session_id) DO UPDATE SET approved=1,approval_basis=excluded.approval_basis,
                    approved_by=excluded.approved_by,approved_at=excluded.approved_at,hidden_at=NULL''',
                    (sid,row['id'],str(uuid4()),1,payload.approval_basis,self.repo.settings.admin_username,time.time()))
            else:
                db.execute('UPDATE event_display_photos SET approved=0,hidden_at=? WHERE session_id=?',(time.time(),sid))
            db.commit()
        return {'approved':payload.approved}


def service(request:Request):return request.app.state.event_display


def kiosk_auth(request:Request):request.app.state.booth_access.require(request)


def display_auth(request:Request):service(request).require(request)


def display_header(request):
    if request.headers.get('X-OSA-Display')!='1':raise HTTPException(403,'Thiếu display header')


class Unlock(BaseModel):code:str=Field(min_length=1,max_length=200)
class Approval(BaseModel):
    approved:StrictBool
    approval_basis:Literal['guest_consent','event_authorization']|None=None
    consent_confirmed:StrictBool=False


@router.get('')
@router.get('/')
def page():return FileResponse(UI/'index.html',headers=HEADERS)


@router.get('/assets/{name}')
def asset(name:Literal['display.js','display.css']):return FileResponse(UI/name,headers=HEADERS)


@router.post('/unlock')
def unlock(request:Request,payload:Unlock,response:Response):
    display_header(request)
    token=service(request).unlock(payload.code,request.client.host)
    response.set_cookie(COOKIE,token,path=PREFIX,httponly=True,samesite='strict',
                        secure=service(request).repo.settings.app_env!='development',max_age=12*3600)
    response.headers.update(HEADERS)
    return {'unlocked':True}


@router.post('/lock',dependencies=[Depends(display_auth)])
def lock(request:Request,response:Response):
    display_header(request)
    with service(request).repo.db.connect() as db:db.execute('DELETE FROM event_display_sessions WHERE token_hash=?',(digest(request.cookies[COOKIE]),))
    response.delete_cookie(COOKIE,path=PREFIX);response.headers.update(HEADERS)
    return {'locked':True}


def approved_photo_feed(display,limit,media_prefix,newest_completion=False):
    items=[]
    order='f.confirmed_at DESC,e.display_id DESC' if newest_completion else 'e.approved_at DESC,e.display_id DESC'
    with display.repo.db.connect() as db:
        rows=db.execute('''SELECT e.display_id,e.approved_at,c.path,c.id,c.session_id,c.width,c.height FROM event_display_photos e
            JOIN session_finals f ON f.session_id=e.session_id AND f.composite_id=e.composite_id
            JOIN sessions s ON s.id=f.session_id AND s.status='completed' AND s.composite_id=f.composite_id
            JOIN composites c ON c.id=e.composite_id WHERE e.approved=1
            ORDER BY '''+order+''' LIMIT ?''',(limit,)).fetchall()
        for row in rows:
            try:display.file(row)
            except HTTPException:continue
            items.append({'id':row['display_id'],'image_url':f"{media_prefix}/{row['display_id']}",
                          'width':row['width'],'height':row['height'],'approved_at':row['approved_at']})
    return {'items':items}


def approved_photo_file(display,display_id):
    with display.repo.db.connect() as db:
        row=db.execute('''SELECT c.path,c.id,c.session_id FROM event_display_photos e
            JOIN session_finals f ON f.session_id=e.session_id AND f.composite_id=e.composite_id
            JOIN sessions s ON s.id=f.session_id AND s.status='completed' AND s.composite_id=f.composite_id
            JOIN composites c ON c.id=e.composite_id WHERE e.display_id=? AND e.approved=1''',(str(display_id),)).fetchone()
        if not row:raise HTTPException(404,'Ảnh không được duyệt trình chiếu.')
        return display.file(row)


@router.get('/api/photos',dependencies=[Depends(display_auth)])
def photos(request:Request,response:Response,limit:int=Query(60,ge=1,le=100)):
    response.headers.update(HEADERS)
    return approved_photo_feed(service(request),limit,f'{PREFIX}/media')


@router.get('/media/{display_id}',dependencies=[Depends(display_auth)])
def media(request:Request,display_id:UUID):
    path=approved_photo_file(service(request),display_id)
    return FileResponse(path,media_type='image/png',headers=HEADERS)


@booth_gallery.get('',dependencies=[Depends(kiosk_auth)])
def booth_photos(request:Request,response:Response,limit:int=Query(8,ge=5,le=10)):
    response.headers.update(HEADERS)
    return approved_photo_feed(service(request),limit,'/api/booth/recent-photos',True)


@booth_gallery.get('/{display_id}',dependencies=[Depends(kiosk_auth)])
def booth_media(request:Request,display_id:UUID):
    return FileResponse(approved_photo_file(service(request),display_id),media_type='image/png',headers=HEADERS)


@admin.get('/status')
def status(request:Request):
    with service(request).repo.db.connect() as db:
        enabled=bool(db.execute('SELECT access_hash FROM event_display_config WHERE id=1').fetchone()[0])
        count=db.execute('SELECT COUNT(*) FROM event_display_photos WHERE approved=1').fetchone()[0]
    return {'enabled':enabled,'approved_count':count}


@admin.post('/access')
def enable(request:Request):return {'code':service(request).access(True),'expires_in_hours':12}


@admin.post('/access/revoke')
def revoke(request:Request):service(request).access(False);return {'enabled':False}


@admin.put('/photos/{sid}')
def approve(request:Request,sid:UUID,payload:Approval):return service(request).approve(str(sid),payload)
