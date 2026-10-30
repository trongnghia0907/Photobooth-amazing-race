"""Public tunnel entry point: photo links only, no booth/admin/API/dev routes.

This process does not start camera, printer or cleanup workers.
"""
from contextlib import asynccontextmanager
import sqlite3
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from .config import Settings
from .guest import router
from .services.repository import Repository
from .logging_filters import install_log_filter
from .runtime_lock import RuntimeLock


def create_public_app(settings=None):
    settings=settings or Settings.from_environment()
    @asynccontextmanager
    async def lifespan(app):
        install_log_filter()
        lease=RuntimeLock(settings.storage_root/'.public-app.lock').acquire()
        try:
            app.state.repository=Repository(settings)
            yield
        finally:lease.close()
    app=FastAPI(title='OSA Public Photo',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.include_router(router)
    @app.get('/healthz')
    def health():
        with app.state.repository.db.connect() as db:db.execute('SELECT 1')
        return {'status':'ok','role':'public-photo'}
    @app.exception_handler(HTTPException)
    async def not_found(request,exc):
        return JSONResponse({'error':{'code':str(exc.status_code),'message':str(exc.detail)}},status_code=exc.status_code)
    @app.exception_handler(OSError)
    @app.exception_handler(sqlite3.Error)
    async def storage_error(request,exc):
        return JSONResponse({'error':{'code':'503','message':'Ảnh tạm thời không truy cập được. Hãy thử lại.'}},status_code=503)
    return app


app=create_public_app()
