"""One durable, immutable public share per confirmed composite revision.

Token = HMAC-SHA256(secret file, random nonce + composite UUID). SQLite stores
the random nonce and token hash, never a plaintext bearer token. The separate
32-byte secret must be backed up with the database to reconstruct owner URLs.
"""
import base64
import hashlib
import hmac
import ipaddress
import re
import secrets
import uuid
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urlsplit

import qrcode
from fastapi import HTTPException

from .images import atomic_write


def public_origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower().rstrip('.')
        parsed.port  # validates numeric/range
        if (parsed.scheme != 'https' or not host or parsed.username or parsed.password
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                or host in {'localhost', 'example.com', 'example.net', 'example.org'}
                or host.endswith(('.localhost', '.local', '.example.com', '.example.net', '.example.org'))):
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            # Public DNS origin (test fixtures use an explicitly named .test origin).
            if ('.' not in host or re.fullmatch(r'[0-9.]+',host)
                or len(host)>253 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in host.split('.'))):
                raise ValueError()
        else:
            if not address.is_global:
                raise ValueError()
        return f'https://{parsed.netloc}'.rstrip('/')
    except (ValueError, TypeError):
        raise HTTPException(503, 'Chưa cấu hình PUBLIC_BASE_URL HTTPS công khai hợp lệ; ảnh đã lưu nhưng QR chưa sẵn sàng.') from None


class SharingService:
    def __init__(self, repository):
        self.repository = repository
        self.settings = repository.settings
        self.key_file = self.settings.storage_root / '.share-key'

    def secret(self, db):
        if not self.key_file.exists():
            if db.execute('SELECT COUNT(*) FROM shares').fetchone()[0]:
                raise HTTPException(503, 'Thiếu share key. Hãy khôi phục key từ backup; không tạo key mới cho link cũ.')
            # First creation runs under Repository.operation's BEGIN IMMEDIATE,
            # serializing other first-finalize requests across workers.
            atomic_write(self.key_file, secrets.token_bytes(32))
            self.key_file.chmod(0o600)
        key = self.key_file.read_bytes()
        if len(key) != 32:
            raise HTTPException(503, 'Share key không hợp lệ; hãy khôi phục từ backup.')
        return key

    def token(self, db, row):
        material = f"{row['nonce']}:{row['composite_id']}".encode()
        raw = hmac.new(self.secret(db), material, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw).decode().rstrip('=')

    def metadata(self, db, composite_id):
        row = db.execute('SELECT * FROM shares WHERE composite_id=? AND revoked_at IS NULL', (composite_id,)).fetchone()
        if row is None or (row['expires_at'] and datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc)):
            return None
        token = self.token(db, row)
        return {
            'final_id': row['id'], 'composite_id': row['composite_id'],
            'share_url': f"{row['public_base_url']}/p/{token}",
            'qr_image_url': f'/p/{token}/qr.png', 'image_url': f'/p/{token}/image',
            'download_url': f'/p/{token}/download', 'qr_embedded': False,
        }

    def finalize(self, sid, owner, operation_key, composite_id):
        repo = self.repository
        def mutate(db, session, paths):
            if session['status'] != 'completed' or session['composite_id'] != composite_id:
                raise HTTPException(409, 'Chỉ tạo QR cho composite hiện tại đã xác nhận hoàn tất.')
            composite = db.execute('SELECT * FROM composites WHERE id=? AND session_id=?', (composite_id, sid)).fetchone()
            if not composite or not (self.settings.storage_root / composite['path']).is_file():
                raise HTTPException(409, 'Ảnh ghép đã lưu không còn tồn tại.')
            existing = db.execute('SELECT * FROM shares WHERE composite_id=?', (composite_id,)).fetchone()
            if existing:
                if existing['revoked_at'] or (existing['expires_at'] and datetime.fromisoformat(existing['expires_at']) <= datetime.now(timezone.utc)):
                    raise HTTPException(409, 'Share đã bị thu hồi/hết hạn; cần một composite revision mới.')
                if not (self.settings.storage_root / existing['qr_path']).is_file():
                    raise HTTPException(503, 'File QR bị mất; cần khôi phục storage.')
                return
            base = public_origin(self.settings.public_base_url)
            share_id, nonce = str(uuid.uuid4()), secrets.token_hex(32)
            token = self.token(db, {'nonce':nonce, 'composite_id':composite_id})
            url = f'{base}/p/{token}'
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
            qr.add_data(url)
            qr.make(fit=True)
            buffer = BytesIO()
            qr.make_image(fill_color='#1E40AF', back_color='white').save(buffer, format='PNG')
            relative = f'qrcodes/{sid}/{share_id}.png'
            path = self.settings.storage_root / relative
            atomic_write(path, buffer.getvalue())
            paths.append(path)
            db.execute('INSERT INTO shares (id,session_id,composite_id,token_hash,nonce,public_base_url,qr_path,created_at) VALUES (?,?,?,?,?,?,?,?)',
                       (share_id,sid,composite_id,hashlib.sha256(token.encode()).hexdigest(),nonce,base,relative,datetime.now(timezone.utc).isoformat()))
        return repo.operation(sid,owner,operation_key,{'action':'finalize','composite_id':composite_id},mutate)

    def lookup(self, token):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise HTTPException(404, 'Link ảnh không hợp lệ hoặc không còn hiệu lực.')
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.repository.db.connect() as db:
            row = db.execute('SELECT s.*,c.path,c.sha256,c.width,c.height FROM shares s JOIN composites c ON c.id=s.composite_id WHERE s.token_hash=?', (token_hash,)).fetchone()
            if row is None or row['revoked_at'] or (row['expires_at'] and datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc)):
                raise HTTPException(404, 'Link ảnh không hợp lệ hoặc không còn hiệu lực.')
            return dict(row)

    def file(self, row, qr=False):
        root = self.settings.storage_root.resolve()
        path = (root / row['qr_path' if qr else 'path']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(404, 'Ảnh không còn trong storage.')
        return path
