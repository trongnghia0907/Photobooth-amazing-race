"""Opt-in public gallery of approved, published composites."""
from io import BytesIO
import os
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image

from .event_display import EventDisplay, HEADERS
from .guest import page as photo_page

UI=Path(__file__).parent/'gallery_ui'
PAGE_SIZE=10
# Use the same publication and official-final records as Event Live Gallery.
# Gallery visibility follows publication approval, independently of QR expiry.
ELIGIBLE='''FROM event_display_photos e
 JOIN session_finals f ON f.session_id=e.session_id AND f.composite_id=e.composite_id
 JOIN sessions s ON s.id=f.session_id AND s.status='completed' AND s.composite_id=f.composite_id
 JOIN composites c ON c.id=f.composite_id
 LEFT JOIN shares h ON h.composite_id=c.id AND h.session_id=s.id
 WHERE e.approved=1 AND e.hidden_at IS NULL AND h.revoked_at IS NULL'''


def enabled(request:Request):
    if not request.app.state.repository.settings.public_gallery_enabled or os.environ.get('MOBILE_QR_TEST_SESSION_ID'):
        raise HTTPException(404,'Not Found')


router=APIRouter(prefix='/gallery',dependencies=[Depends(enabled)])


@router.get('')
@router.get('/')
def page():
    return FileResponse(UI/'index.html',headers=HEADERS)


@router.get('/assets/{name}')
def asset(name:Literal['gallery.js','gallery.css','theme-gallery.png']):
    if name=='theme-gallery.png':
        return FileResponse(UI.parents[2]/'theme'/name,media_type='image/png',headers=HEADERS)
    return FileResponse(UI/name,headers=HEADERS)


@router.get('/api/photos')
def photos(request:Request,page:str='1'):
    repo=request.app.state.repository
    try:number=max(1,int(page))
    except ValueError:number=1
    with repo.db.connect() as db:
        db.execute('BEGIN')
        total=db.execute('SELECT COUNT(*) '+ELIGIBLE).fetchone()[0]
        pages=max(1,(total+PAGE_SIZE-1)//PAGE_SIZE);number=min(number,pages)
        rows=db.execute('SELECT e.display_id,c.width,c.height '+ELIGIBLE+
                        ' ORDER BY f.confirmed_at DESC,e.display_id DESC LIMIT ? OFFSET ?',
                        (PAGE_SIZE,(number-1)*PAGE_SIZE)).fetchall()
        items=[]
        for row in rows:
            items.append({'id':row['display_id'],'preview_url':'/gallery/preview/'+row['display_id'],
                          'photo_url':'/gallery/photo/'+row['display_id'],
                          'width':row['width'],'height':row['height']})
    return JSONResponse({'items':items,'total':total,'page':number,'pages':pages,'page_size':PAGE_SIZE},headers=HEADERS)


def published_file(request: Request, display_id: UUID):
    repo=request.app.state.repository
    with repo.db.connect() as db:
        row=db.execute('SELECT c.* '+ELIGIBLE+' AND e.display_id=?',
                       (str(display_id),)).fetchone()
    if not row:raise HTTPException(404,'Photo unavailable')
    return EventDisplay(repo).file(row,verify=True)


@router.get('/photo/{display_id}')
def detail(request: Request, display_id: UUID):
    published_file(request, display_id)
    url = f'/gallery/photo/{display_id}'
    return photo_page(f'<img id="guestPhoto" src="{url}/image" alt="Ảnh sự kiện">'
                      f'<a id="guestDownload" href="{url}/download" download>Tải ảnh về máy</a>')


@router.get('/photo/{display_id}/image')
def image(request: Request, display_id: UUID):
    return FileResponse(published_file(request, display_id), media_type='image/png', headers=HEADERS)


@router.get('/photo/{display_id}/download')
def download(request: Request, display_id: UUID):
    return FileResponse(published_file(request, display_id), media_type='image/png',
                        filename=f'amazing-race-2026-photo-{display_id}.png', headers=HEADERS)


@router.get('/preview/{display_id}')
def preview(request: Request, display_id: UUID):
    path=published_file(request, display_id)
    try:
        with Image.open(path) as source:
            image=source.convert('RGB');image.thumbnail((600,600),Image.Resampling.LANCZOS)
            output=BytesIO();image.save(output,'JPEG',quality=82,optimize=True)
    except OSError:
        raise HTTPException(503,'Photo temporarily unavailable') from None
    return Response(output.getvalue(),media_type='image/jpeg',headers=HEADERS)
