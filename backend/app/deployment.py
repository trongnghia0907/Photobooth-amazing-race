"""Production assets only; no SPA wildcard can swallow /api or /p."""
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

KIOSK_HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
 'Content-Security-Policy':"default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"}


def index(request:Request):
    root=request.app.state.settings.frontend_dist
    if not root:raise HTTPException(404,'Frontend chưa được cấu hình')
    return FileResponse(root/'index.html',headers=KIOSK_HEADERS)


def install(app,settings):
    if not settings.frontend_dist:return
    root=Path(settings.frontend_dist).resolve()
    if not (root/'index.html').is_file() or not (root/'assets').is_dir():
        raise ValueError('Không tìm thấy frontend đã build. Chạy npm.cmd run build:host và đặt OSA_FRONTEND_DIST tới dist-host.')
    app.mount('/assets',StaticFiles(directory=root/'assets',follow_symlink=False),name='kiosk-assets')
    app.add_api_route('/booth',index,methods=['GET'],include_in_schema=False)
    app.add_api_route('/booth/',index,methods=['GET'],include_in_schema=False)
