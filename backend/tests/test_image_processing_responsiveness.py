"""Normalization must not run on the ASGI event-loop thread."""
import asyncio
from io import BytesIO
import threading

from fastapi import UploadFile
from starlette.datastructures import Headers
from app.config import Settings
from app.services import images


def test_upload_validation_does_not_block_event_loop(tmp_path,monkeypatch):
    entered=threading.Event();released=threading.Event();owner=threading.get_ident();calls=[]
    def validate(*args):
        calls.append(threading.get_ident());entered.set()
        assert released.wait(3),'Event loop was blocked by image processing'
        return 'validated'
    monkeypatch.setattr(images,'validate_image',validate)
    async def check():
        file=UploadFile(BytesIO(b'fixture'),headers=Headers({'content-type':'image/png'}))
        pending=asyncio.create_task(images.read_image(file,Settings(tmp_path)))
        try:
            assert await asyncio.to_thread(entered.wait,2)
            assert calls==[calls[0]] and calls[0]!=owner
            released.set()
            assert await pending=='validated'
        finally:
            released.set();await pending
    asyncio.run(check())
