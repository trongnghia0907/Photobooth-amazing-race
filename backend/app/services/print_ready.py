"""Immutable derivative: append a separate QR footer, never cover the composite."""
import hashlib
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from fastapi import HTTPException
from .images import atomic_write
from .repository import now


class PrintReadyService:
    def __init__(self, repository):
        self.repo = repository
        self._lock = threading.Lock()
        self._executor = None
        self._pending = set()

    def prepare_async(self, final_id):
        """Optional derivative work must never hold up public QR readiness."""
        with self._lock:
            if final_id in self._pending or len(self._pending) >= 8:
                return
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='print-ready')
            self._pending.add(final_id)
            self._executor.submit(self._prepare, final_id)

    def _prepare(self, final_id):
        started = time.perf_counter()
        try:
            self.backfill(final_id)
            logging.getLogger(__name__).info('print_ready_ms=%.1f', (time.perf_counter()-started)*1000)
        except Exception as error:
            # The durable original and share remain available for a later retry.
            logging.getLogger(__name__).warning('print_ready_failed: %s', type(error).__name__)
        finally:
            with self._lock:
                self._pending.discard(final_id)

    def close(self):
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)

    def url(self, db, final_id):
        from .sharing import is_local_origin,is_lan_origin
        row=db.execute('SELECT * FROM shares WHERE id=?',(final_id,)).fetchone()
        if not row or row['revoked_at'] or (row['expires_at'] and row['expires_at'] <= now()):
            return None
        cloud = self.repo.cloud
        if cloud.configured:
            publication = db.execute('SELECT * FROM cloud_publications WHERE composite_id=?',
                                     (row['composite_id'],)).fetchone()
            return cloud.ready_url(publication)
        try:origin=self.repo.sharing.origin()
        except HTTPException:return None
        if not origin.startswith('https://') or is_local_origin(origin) or is_lan_origin(origin):return None
        try:return f"{origin}/p/{self.repo.sharing.token(db,row)}"
        except HTTPException:return None  # Existing bearer links still authorize the durable original.

    def current(self,db,final_id):
        url=self.url(db,final_id)
        stored=db.execute('SELECT value FROM host_settings WHERE key=?',('print-ready-qr-only-url:'+final_id,)).fetchone()
        if not url or not stored or stored['value']!=url:return None
        return db.execute('SELECT * FROM print_ready WHERE final_id=?',(final_id,)).fetchone()

    def ensure(self, db, final_id, paths):
        url=self.url(db,final_id)
        if not url:return None
        existing = self.current(db,final_id)
        if existing:
            return existing
        self.repo.ensure_disk_space()
        row = db.execute('SELECT s.*,c.path FROM shares s JOIN composites c ON c.id=s.composite_id WHERE s.id=?', (final_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Không tìm thấy ảnh đã xác nhận')
        root = self.repo.settings.storage_root.resolve()
        source = (root / row['path']).resolve()
        qr_path = (root / row['qr_path']).resolve()
        if not source.is_relative_to(root) or not qr_path.is_relative_to(root):
            raise HTTPException(404, 'Không tìm thấy ảnh')
        with Image.open(source) as original, Image.open(BytesIO(self.repo.sharing.qr_bytes(url))) as qr:
            # Integer QR module scaling retains quiet zone and crisp edges.
            width = original.width
            height = original.height
            modules = qr.width // 10
            margin = max(4, width * 45 // 1000)
            qr_target = width * 10 // 100
            module_scale = max(1, qr_target // modules)
            qr_size = modules * module_scale
            footer = max(width * 11 // 100, qr_size + 2 * margin)
            if width * (height + footer) > self.repo.settings.max_image_pixels * 2:
                raise HTTPException(422, 'Tỷ lệ/kích thước composite không phù hợp để tạo bản in. Giữ ảnh gốc; hãy chỉnh frame và xác nhận lại.')
            canvas = Image.new('RGBA', (width, height + footer), 'white')
            canvas.paste(original.convert('RGBA'), (0, 0))
            x, y = width - margin - qr_size, height + (footer - qr_size) // 2
            canvas.paste(qr.convert('RGB').resize((qr_size, qr_size), Image.Resampling.NEAREST), (x, y))
            draw = ImageDraw.Draw(canvas)
            title = 'AMAZING RACE 2026'
            font = ImageFont.truetype('arialbd.ttf', max(12, footer * 27 // 100))
            bounds = draw.textbbox((0, 0), title, font=font, stroke_width=max(1, width // 2400))
            text_height = bounds[3] - bounds[1]
            text_width = bounds[2] - bounds[0]
            title_max_width = width - 2 * margin - qr_size - margin
            if text_width > title_max_width:
                font = ImageFont.truetype('arialbd.ttf', max(12, footer * 20 // 100))
                bounds = draw.textbbox((0, 0), title, font=font)
                text_width = bounds[2] - bounds[0]
                text_height = bounds[3] - bounds[1]
            ty = height + (footer - text_height) // 2 - bounds[1]
            draw.text((margin, ty), title, font=font, fill='#15365b',
                      stroke_width=max(1, width // 2400), stroke_fill='#49c8ee')
            output = BytesIO()
            if canvas.getextrema()[3] == (255, 255):
                canvas = canvas.convert('RGB')
            canvas.save(output, 'PNG')
        data = output.getvalue()
        version=hashlib.sha256(url.encode()).hexdigest()[:20]
        relative = f"print_ready/{row['session_id']}/{final_id}-{version}-qr-only.png"
        target = root / relative
        atomic_write(target, data)
        paths.append(target)
        db.execute('''INSERT INTO print_ready VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(final_id) DO UPDATE SET path=excluded.path,sha256=excluded.sha256,
                   width=excluded.width,height=excluded.height,source_height=excluded.source_height,
                   qr_x=excluded.qr_x,qr_y=excluded.qr_y,qr_size=excluded.qr_size,created_at=excluded.created_at''',
                   (final_id, relative, hashlib.sha256(data).hexdigest(), width, height + footer, height, x, y, qr_size, now()))
        db.execute('INSERT INTO host_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                   ('print-ready-qr-only-url:'+final_id,url))
        return db.execute('SELECT * FROM print_ready WHERE final_id=?', (final_id,)).fetchone()

    def backfill(self, final_id):
        paths = []
        with self.repo.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                self.ensure(db, final_id, paths)
                db.commit()
            except Exception:
                db.rollback()
                for path in paths:
                    path.unlink(missing_ok=True)
                raise
