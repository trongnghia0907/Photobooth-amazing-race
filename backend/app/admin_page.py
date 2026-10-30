from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter()
UI = Path(__file__).parent/'admin_ui'
HEADERS = {'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"}


@router.get('/')
def root(request:Request):
    if request.app.state.settings.frontend_dist:
        from .deployment import index
        return index(request)
    return RedirectResponse('/admin',status_code=307)


@router.get('/admin')
@router.get('/admin/')
def shell():
    # The public shell contains no data. Every gallery/image/action is authenticated.
    return FileResponse(UI/'index.html',headers=HEADERS)


@router.get('/admin/assets/{name}')
def asset(name: Literal['dashboard.js','dashboard.css']):
    return FileResponse(UI/name,headers=HEADERS)
