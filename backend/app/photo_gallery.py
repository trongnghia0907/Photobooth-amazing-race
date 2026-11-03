"""Opt-in, read-only public gallery of published finals with unexpired shares."""
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import hmac
import os
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image

from .event_display import EventDisplay, HEADERS

UI=Path(__file__).parent/'gallery_ui'
PAGE_SIZE=10
# Use the same publication and official-final records as Event Live Gallery.
# This additional public surface also requires an already-issued share expiry.
ELIGIBLE='''FROM event_display_photos e
 JOIN session_finals f ON f.session_id=e.session_id AND f.composite_id=e.composite_id
 JOIN sessions s ON s.id=f.session_id AND s.status='completed' AND s.composite_id=f.composite_id
 JOIN composites c ON c.id=f.composite_id
 JOIN shares h ON h.composite_id=c.id AND h.session_id=s.id
 WHERE e.approved=1 AND e.hidden_at IS NULL AND h.revoked_at IS NULL
 AND h.expires_at IS NOT NULL AND julianday(h.expires_at)>julianday(?)'''
FIELDS='c.*,e.display_id,h.nonce,h.composite_id,h.token_hash,h.expires_at'


def enabled(request:Request):
    if not request.app.state.repository.settings.public_gallery_enabled or os.environ.get('MOBILE_QR_TEST_SESSION_ID'):
        raise HTTPException(404,'Not Found')


router=APIRouter(prefix='/gallery',dependencies=[Depends(enabled)])


@router.get('')
@router.get('/')
def page():
    return FileResponse(UI/'index.html',headers=HEADERS)


@router.get('/assets/{name}')
def asset(name:Literal['gallery.js','gallery.css']):
    return FileResponse(UI/name,headers=HEADERS)


@router.get('/api/photos')
def photos(request:Request,page:str='1'):
    repo=request.app.state.repository
    stamp=datetime.now(timezone.utc).isoformat()
    try:number=max(1,int(page))
    except ValueError:number=1
    with repo.db.connect() as db:
        db.execute('BEGIN')
        total=db.execute('SELECT COUNT(*) '+ELIGIBLE,(stamp,)).fetchone()[0]
        pages=max(1,(total+PAGE_SIZE-1)//PAGE_SIZE);number=min(number,pages)
        rows=db.execute('SELECT '+FIELDS+' '+ELIGIBLE+
                        ' ORDER BY f.confirmed_at DESC,e.display_id DESC LIMIT ? OFFSET ?',
                        (stamp,PAGE_SIZE,(number-1)*PAGE_SIZE)).fetchall()
        items=[]
        for row in rows:
            # Reconstruct only an existing stable token. Never finalize, create,
            # renew, or write share metadata while listing the public gallery.
            token=repo.sharing.token(db,row)
            if not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),row['token_hash']):
                raise HTTPException(503,'The photo gallery is temporarily unavailable.')
            items.append({'id':row['display_id'],'preview_url':'/gallery/preview/'+row['display_id'],
                          'photo_url':'/p/'+token,'width':row['width'],'height':row['height'],
                          'expires_at':row['expires_at']})
    return JSONResponse({'items':items,'total':total,'page':number,'pages':pages,'page_size':PAGE_SIZE},headers=HEADERS)


@router.get('/preview/{display_id}')
def preview(request:Request,display_id:UUID):
    repo=request.app.state.repository
    with repo.db.connect() as db:
        row=db.execute('SELECT '+FIELDS+' '+ELIGIBLE+' AND e.display_id=?',
                       (datetime.now(timezone.utc).isoformat(),str(display_id))).fetchone()
    if not row:raise HTTPException(404,'Photo unavailable')
    # Existing storage/Drive recovery guard; no new image store or upload path.
    path=EventDisplay(repo).file(row,verify=True)
    try:
        with Image.open(path) as source:
            image=source.convert('RGB');image.thumbnail((600,600),Image.Resampling.LANCZOS)
            output=BytesIO();image.save(output,'JPEG',quality=82,optimize=True)
    except OSError:
        raise HTTPException(503,'Photo temporarily unavailable') from None
    return Response(output.getvalue(),media_type='image/jpeg',headers=HEADERS)
