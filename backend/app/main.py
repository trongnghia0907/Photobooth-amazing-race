from contextlib import asynccontextmanager
import logging
import sqlite3

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings
from .routers import router
from .services.repository import Repository

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
        app.state.settings = settings
        app.state.repository = Repository(settings)
        yield

    app = FastAPI(title='OSA Photobooth — Phase 2', lifespan=lifespan)
    app.add_middleware(BodyLimit, limit=settings.max_upload_bytes + 64 * 1024)
    app.include_router(router)

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
