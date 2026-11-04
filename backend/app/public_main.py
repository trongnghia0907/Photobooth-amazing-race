"""Public tunnel entry point: photo links only, no booth/admin/API/dev routes.

This process does not start camera, printer or cleanup workers.
"""
from contextlib import asynccontextmanager
import sqlite3
import os
import hashlib
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from .config import Settings
from .guest import router
from .services.repository import Repository
from .logging_filters import install_log_filter
from .runtime_lock import RuntimeLock
from .photo_gallery import router as photo_gallery_router


def create_public_app(settings=None):
    settings=settings or Settings.from_environment()
    @asynccontextmanager
    async def lifespan(app):
        install_log_filter()
        lease=RuntimeLock(settings.storage_root/'.public-app.lock').acquire()
        try:
            app.state.repository=Repository(settings)
            try:
                yield
            finally:
                app.state.repository.print_ready.close()
        finally:lease.close()
    app=FastAPI(title='AMAZING RACE 2026 Guest Photo',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.include_router(router)
    app.include_router(photo_gallery_router)
    # Optional disposable-session restriction for integration testing. Applied
    # before any image/Drive retrieval; production sharing remains unchanged.
    test_session=os.environ.get('MOBILE_QR_TEST_SESSION_ID')
    if test_session:
        @app.middleware('http')
        async def test_photo_only(request,call_next):
            parts=request.url.path.split('/')
            if len(parts)>=3 and parts[1]=='p' and len(parts[2])==43:
                with app.state.repository.db.connect() as db:
                    allowed=db.execute('SELECT 1 FROM shares WHERE session_id=? AND token_hash=?',
                        (test_session,hashlib.sha256(parts[2].encode()).hexdigest())).fetchone()
                if not allowed:return JSONResponse({'error':{'code':'404','message':'Not Found'}},status_code=404)
            return await call_next(request)
    def health():
        with app.state.repository.db.connect() as db:db.execute('SELECT 1')
        return {'status':'ok','role':'public-photo'}
    if os.environ.get('MOBILE_QR_PHOTO_ONLY')!='true':
        app.get('/healthz')(health)
    @app.exception_handler(HTTPException)
    async def not_found(request,exc):
        return JSONResponse({'error':{'code':str(exc.status_code),'message':str(exc.detail)}},status_code=exc.status_code)
    @app.exception_handler(OSError)
    @app.exception_handler(sqlite3.Error)
    async def storage_error(request,exc):
        return JSONResponse({'error':{'code':'503','message':'Ảnh tạm thời không truy cập được. Hãy thử lại.'}},status_code=503)
    return app


app=create_public_app()
