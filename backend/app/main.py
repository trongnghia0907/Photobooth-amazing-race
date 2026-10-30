from contextlib import asynccontextmanager, ExitStack
import logging
import sqlite3
import ipaddress

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings
from .routers import router
from .guest import router as guest_router
from .logging_filters import install_log_filter
from .services.repository import Repository
from .services.printing import PrintingService
from .services.admin_auth import AdminAuth
from .printing_routes import router as printing_router, admin as admin_router
from .admin_page import router as admin_page_router
from .services.camera.controller import CameraController
from .services.camera.base import CameraError
from .camera_routes import router as camera_router, admin as camera_admin_router
from .booth_access import BoothAccess,router as booth_router
from .runtime_lock import RuntimeLock
from .deployment import install as install_frontend
from .event_display import EventDisplay,router as event_router,admin as event_admin,HEADERS as EVENT_HEADERS

logger = logging.getLogger(__name__)


class UploadTooLarge(HTTPException):
    def __init__(self):
        super().__init__(413, 'Request vượt giới hạn dung lượng')


class BodyLimit:
    """Limit total request bytes, including chunked bodies before multipart spooling."""
    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        try:
            oversized = int(headers.get(b'content-length', b'0')) > self.limit
        except ValueError:
            oversized = True
        if oversized:
            return await error_response(413, 'Request vượt giới hạn dung lượng')(scope, receive, send)
        total = 0
        async def limited_receive():
            nonlocal total
            message = await receive()
            total += len(message.get('body', b''))
            if total > self.limit:
                raise UploadTooLarge()
            return message
        await self.app(scope, limited_receive, send)


def error_response(status, message):
    return JSONResponse(status_code=status, content={'error': {'code': str(status), 'message': message}})


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_environment()

    @asynccontextmanager
    async def lifespan(app):
        install_log_filter()
        app.state.settings = settings
        # Release earlier workers/leases even if a later startup stage fails.
        with ExitStack() as cleanup:
            if settings.frontend_dist:
                cleanup.callback(RuntimeLock(settings.storage_root/'.host-app.lock').acquire().close)
            app.state.repository = Repository(settings)
            app.state.booth_access = BoothAccess(app.state.repository)
            app.state.event_display = EventDisplay(app.state.repository)
            app.state.admin_auth = AdminAuth(app.state.repository)
            app.state.printing = PrintingService(app.state.repository)
            cleanup.callback(app.state.printing.stop)
            app.state.printing.start()
            app.state.camera = CameraController(app.state.repository)
            cleanup.callback(app.state.camera.stop)
            app.state.camera.start()
            cleanup.callback(app.state.repository.temporary_assets.stop)
            app.state.repository.temporary_assets.start()
            yield

    app = FastAPI(title='OSA Photobooth — Phase 6', lifespan=lifespan,
                  docs_url=None if settings.frontend_dist else '/docs',
                  redoc_url=None if settings.frontend_dist else '/redoc',
                  openapi_url=None if settings.frontend_dist else '/openapi.json')
    app.add_middleware(BodyLimit, limit=settings.max_upload_bytes + 64 * 1024)
    app.include_router(router)
    app.include_router(guest_router)
    app.include_router(printing_router)
    app.include_router(admin_router)
    app.include_router(admin_page_router)
    app.include_router(camera_router)
    app.include_router(camera_admin_router)
    app.include_router(booth_router)
    app.include_router(event_router)
    app.include_router(event_admin)
    install_frontend(app,settings)

    @app.middleware('http')
    async def deployment_permissions(request,call_next):
        if settings.frontend_dist:
            try:
                path=request.url.path
                if path.startswith(('/admin','/api/admin')):
                    try:
                        address=ipaddress.ip_address(request.client.host)
                        local=(getattr(address,'ipv4_mapped',None) or address).is_loopback
                    except ValueError:local=False
                    if not local:raise HTTPException(403,'Host Dashboard chỉ được mở trên laptop host')
                if path.startswith('/api/sessions') or path=='/api/print-config':
                    request.app.state.booth_access.check_request(request)
                    if settings.app_env!='development' and request.method=='POST' and path.endswith('/photos'):
                        raise HTTPException(403,'Production chỉ nhận file chụp từ camera adapter trên host')
            except HTTPException as exc:return error_response(exc.status_code,str(exc.detail))
        response=await call_next(request)
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store'
        return response

    @app.exception_handler(CameraError)
    async def camera_error(request, exc):
        status = 409 if exc.code in ('busy','host_busy','not_connected','adapter_changed','disabled') else 504 if exc.code=='timeout' else 503
        return JSONResponse(status_code=status,content={'error':{'code':exc.code,'message':str(exc),'stage':exc.stage,'uncertain':exc.uncertain,'capture_id':getattr(exc,'capture_id',None)}})

    @app.middleware('http')
    async def admin_privacy(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/event-display'):
            response.headers.update(EVENT_HEADERS)
        if request.url.path.startswith(('/api/admin','/admin')):
            response.headers.update({'Cache-Control':'no-store','X-Robots-Tag':'noindex, nofollow','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'})
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc):
        return error_response(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc):
        # Never echo credentials, customer data or request bodies in errors.
        return error_response(422, 'Dữ liệu request không hợp lệ')

    @app.exception_handler(UploadTooLarge)
    async def body_error(request: Request, exc):
        return error_response(413, 'Request vượt giới hạn dung lượng')

    @app.exception_handler(OSError)
    @app.exception_handler(sqlite3.Error)
    async def storage_error(request: Request, exc):
        logger.error('Storage operation failed (%s)', type(exc).__name__)
        return error_response(503, 'Không thể lưu dữ liệu. Hãy kiểm tra ổ đĩa và thử lại.')

    return app


app = create_app()
