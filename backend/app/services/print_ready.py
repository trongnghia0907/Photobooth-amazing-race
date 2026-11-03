"""Immutable derivative: append a separate QR footer, never cover the composite."""
import hashlib
from io import BytesIO
from PIL import Image, ImageDraw
from fastapi import HTTPException
from .images import atomic_write
from .repository import now


class PrintReadyService:
    def __init__(self, repository):
        self.repo = repository

    def url(self, db, final_id):
        from .sharing import is_local_origin,is_lan_origin
        row=db.execute('SELECT * FROM shares WHERE id=?',(final_id,)).fetchone()
        if not row:return None
        try:origin=self.repo.sharing.origin()
        except HTTPException:return None
        if not origin.startswith('https://') or is_local_origin(origin) or is_lan_origin(origin):return None
        return f"{origin}/p/{self.repo.sharing.token(db,row)}"

    def current(self,db,final_id):
        url=self.url(db,final_id)
        stored=db.execute('SELECT value FROM host_settings WHERE key=?',('print-ready-url:'+final_id,)).fetchone()
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
            width = max(640,original.width)
            height = original.height
            modules = qr.width // 10
            qr_size = modules * max(1, min(6, width // (modules * 2)))
            margin = max(24, width // 40)
            footer = qr_size + 2 * margin
            if width * (height + footer) > self.repo.settings.max_image_pixels * 2:
                raise HTTPException(422, 'Tỷ lệ/kích thước composite không phù hợp để tạo bản in. Giữ ảnh gốc; hãy chỉnh frame và xác nhận lại.')
            canvas = Image.new('RGB', (width, height + footer), 'white')
            composite = original.convert('RGBA')
            canvas.paste(composite, (0, 0), composite)
            x, y = width - margin - qr_size, height + margin
            canvas.paste(qr.convert('RGB').resize((qr_size, qr_size), Image.Resampling.NEAREST), (x, y))
            draw = ImageDraw.Draw(canvas)
            draw.text((margin, height + margin), 'AMAZING RACE 2026', fill='#1e40af')
            draw.text((margin, height + margin + 24), 'Scan to view / download', fill='black')
            from .sharing import is_local_origin,is_lan_origin
            if is_local_origin(row['public_base_url']):
                draw.text((margin, height + margin + 48), 'LOCAL TEST - this computer only', fill='#9a3412')
            elif is_lan_origin(row['public_base_url']):
                draw.text((margin,height+margin+48),'LAN TEST - same Wi-Fi only',fill='#9a3412')
            output = BytesIO()
            canvas.save(output, 'PNG')
        data = output.getvalue()
        version=hashlib.sha256(url.encode()).hexdigest()[:20]
        relative = f"print_ready/{row['session_id']}/{final_id}-{version}.png"
        target = root / relative
        atomic_write(target, data)
        paths.append(target)
        db.execute('''INSERT INTO print_ready VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(final_id) DO UPDATE SET path=excluded.path,sha256=excluded.sha256,
                   width=excluded.width,height=excluded.height,source_height=excluded.source_height,
                   qr_x=excluded.qr_x,qr_y=excluded.qr_y,qr_size=excluded.qr_size,created_at=excluded.created_at''',
                   (final_id, relative, hashlib.sha256(data).hexdigest(), width, height + footer, height, x, y, qr_size, now()))
        db.execute('INSERT INTO host_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                   ('print-ready-url:'+final_id,url))
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
