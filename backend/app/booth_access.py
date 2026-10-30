"""Paired kiosk permission is separate from an owner token and a public QR."""
import hashlib
import hmac
import secrets
import threading
import time
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

COOKIE='osa_booth'
router=APIRouter(prefix='/api/booth')


class RateLimit:
    def __init__(self):self.entries={};self.lock=threading.Lock()
    def check(self,scope,limit,operation=None):
        with self.lock:
            now=time.monotonic()
            self.entries={k:[v for v in values if v[0]>now-60] for k,values in self.entries.items() if any(v[0]>now-60 for v in values)}
            rows=self.entries.setdefault(scope,[])
            if operation and any(v[1]==operation for v in rows):return
            if len(rows)>=limit or len(self.entries)>2000:raise HTTPException(429,'Quá nhiều yêu cầu. Chờ một phút rồi thử lại cùng yêu cầu.')
            rows.append((now,operation or secrets.token_hex(8)))


class BoothAccess:
    def __init__(self,repo):self.repo=repo;self.settings=repo.settings;self.limiter=RateLimit()
    @property
    def enabled(self):return bool(self.settings.frontend_dist)
    @staticmethod
    def csrf(token):return hmac.new(token.encode(),b'OSA booth CSRF',hashlib.sha256).hexdigest()
    def pair(self,key,ip,existing=''):
        self.limiter.check(('pair',ip),5)
        if not self.enabled:raise HTTPException(404,'Kiosk pairing chưa được bật')
        if not hmac.compare_digest(key.encode(),self.settings.booth_pairing_key.encode()):raise HTTPException(401,'Mã ghép kiosk không đúng')
        tag=hashlib.sha256(self.settings.booth_pairing_key.encode()).hexdigest();stamp=time.time()
        with self.repo.db.connect() as db:
            previous=db.execute('SELECT 1 FROM booth_stations WHERE token_hash=? AND auth_tag=?',(hashlib.sha256(existing.encode()).hexdigest(),tag)).fetchone() if existing else None
            token=existing if previous else secrets.token_urlsafe(32)
            db.execute('INSERT INTO booth_stations VALUES (?,?,?,?) ON CONFLICT(token_hash) DO UPDATE SET expires_at=excluded.expires_at',(hashlib.sha256(token.encode()).hexdigest(),tag,stamp+12*3600,stamp))
        return token

    def require(self,request,mutation=False):
        token=request.cookies.get(COOKIE,'')
        with self.repo.db.connect() as db:
            row=db.execute('SELECT * FROM booth_stations WHERE token_hash=? AND auth_tag=? AND expires_at>?',
                           (hashlib.sha256(token.encode()).hexdigest(),hashlib.sha256(self.settings.booth_pairing_key.encode()).hexdigest(),time.time())).fetchone()
        if not row:raise HTTPException(401,'Thiết bị cần được người vận hành ghép kiosk')
        if mutation and not hmac.compare_digest(request.headers.get('X-Booth-CSRF','').encode(),self.csrf(token).encode()):
            raise HTTPException(403,'Thiếu CSRF token của kiosk')
        return row['token_hash']

    def check_request(self,request):
        station=self.require(request,request.method not in ('GET','HEAD','OPTIONS'))
        parts=request.url.path.split('/')
        if len(parts)>3 and parts[2]=='sessions':
            sid=parts[3]
            with self.repo.db.connect() as db:
                row=db.execute('SELECT 1 FROM booth_sessions WHERE session_id=? AND station_hash=?',(sid,station)).fetchone()
            if not row:raise HTTPException(404,'Phiên không thuộc thiết bị kiosk này')
        if request.method=='POST':
            route='capture' if request.url.path.endswith('/camera/captures') else 'print' if request.url.path.endswith('/print-jobs') else 'session' if request.url.path=='/api/sessions' else None
            if route:self.limiter.check((route,station),{'capture':30,'print':6,'session':12}[route],request.headers.get('Idempotency-Key'))
        request.state.station_hash=station

    def bind(self,sid,station):
        with self.repo.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT station_hash FROM booth_sessions WHERE session_id=?',(sid,)).fetchone()
            if row and row['station_hash']!=station:raise HTTPException(404,'Phiên không thuộc kiosk')
            db.execute('INSERT OR IGNORE INTO booth_sessions VALUES (?,?)',(sid,station));db.commit()


class Pairing(BaseModel):key:str=Field(min_length=1,max_length=1000)


@router.post('/pair')
def pair(request:Request,payload:Pairing,response:Response):
    if request.headers.get('X-OSA-Pair')!='1':raise HTTPException(403,'Thiếu pairing header')
    service=request.app.state.booth_access;token=service.pair(payload.key,request.client.host,request.cookies.get(COOKIE,''))
    response.set_cookie(COOKIE,token,path='/api',httponly=True,samesite='strict',secure=service.settings.app_env!='development',max_age=12*3600)
    response.headers['Cache-Control']='no-store'
    return {'required':True,'csrf_token':service.csrf(token)}


@router.get('/me')
def me(request:Request):
    service=request.app.state.booth_access
    if not service.enabled:return {'required':False}
    service.require(request)
    return {'required':True,'csrf_token':service.csrf(request.cookies[COOKIE])}


@router.post('/logout')
def logout(request:Request,response:Response):
    service=request.app.state.booth_access;station=service.require(request,True)
    with service.repo.db.connect() as db:db.execute('UPDATE booth_stations SET expires_at=0 WHERE token_hash=?',(station,))
    response.delete_cookie(COOKIE,path='/api');return {'paired':False}
