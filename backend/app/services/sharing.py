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


def is_local_origin(value: str) -> bool:
    try:
        host = (urlsplit(value).hostname or '').lower().rstrip('.')
    except ValueError:
        return False
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_lan_origin(value: str) -> bool:
    try:
        address=ipaddress.ip_address(urlsplit(value).hostname or '')
        return address.version==4 and any(address in ipaddress.ip_network(network) for network in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
    except ValueError:return False


def public_origin(value: str, *, allow_local=False, allow_lan=False) -> str:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower().rstrip('.')
        parsed.port  # validates numeric/range
        if (not host or parsed.username or parsed.password
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                or any(character.isspace() for character in value)
                or host in {'example.com', 'example.net', 'example.org'}
                or host.endswith(('.localhost', '.local', '.example.com', '.example.net', '.example.org'))):
            raise ValueError()
        if allow_local and is_local_origin(value) and parsed.scheme in {'http', 'https'}:
            return f'{parsed.scheme}://{parsed.netloc}'
        if allow_lan and is_lan_origin(value) and parsed.scheme in {'http','https'}:
            return f'{parsed.scheme}://{parsed.netloc}'
        if parsed.scheme != 'https' or is_local_origin(value):
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
        if not value:
            message = 'Chưa đặt PUBLIC_BASE_URL. Để thử trên máy này: chạy python scripts/run_local_backend.py từ thư mục dự án, rồi xác nhận ảnh. Điện thoại khác cần URL HTTPS công khai.'
        elif is_local_origin(value) and not allow_local:
            message = 'PUBLIC_BASE_URL là localhost nhưng APP_ENV chưa phải development. Test local cần APP_ENV=development và PUBLIC_BASE_URL=http://localhost:8000; sau đó khởi động lại backend.'
        else:
            message = 'PUBLIC_BASE_URL không hợp lệ. Production cần origin HTTPS công khai; development cho phép http://localhost:8000. Không dùng path, query, credentials hoặc IP mạng riêng.'
        raise HTTPException(503, message) from None


class SharingService:
    def __init__(self, repository):
        self.repository = repository
        self.settings = repository.settings
        self.key_file = self.settings.storage_root / '.share-key'

    def configuration(self):
        try:
            origin = public_origin(self.settings.public_base_url, allow_local=self.settings.app_env == 'development',allow_lan=self.settings.app_env=='development' and self.settings.allow_lan_http)
            local = is_local_origin(origin)
            lan=is_lan_origin(origin)
            return {'configured': True, 'app_env': self.settings.app_env, 'base_url': origin, 'local_only': local,'lan_only':lan,
                    'message': 'QR localhost chỉ mở trên máy này, không dùng được trên điện thoại khác.' if local else 'QR LAN chỉ dùng trên cùng Wi-Fi, không dùng qua 4G/5G.' if lan else 'URL HTTPS công khai đã được cấu hình; cần kiểm tra truy cập thực tế.'}
        except HTTPException as error:
            return {'configured': False, 'app_env': self.settings.app_env, 'base_url': None, 'local_only': False, 'message': str(error.detail)}

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
        ready = db.execute('SELECT * FROM print_ready WHERE final_id=?', (row['id'],)).fetchone()
        return {
            'final_id': row['id'], 'composite_id': row['composite_id'],
            'share_url': f"{row['public_base_url']}/p/{token}",
            'qr_image_url': f'/p/{token}/qr.png', 'image_url': f'/p/{token}/image',
            'download_url': f'/p/{token}/download', 'qr_embedded': bool(ready),
            'print_ready': {k: ready[k] for k in ('sha256','width','height','source_height','qr_x','qr_y','qr_size')} if ready else None,
            'local_only': is_local_origin(row['public_base_url']),
            'lan_only': is_lan_origin(row['public_base_url']),
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
                repo.print_ready.ensure(db, existing['id'], paths)
                return
            base = public_origin(self.settings.public_base_url, allow_local=self.settings.app_env == 'development',allow_lan=self.settings.app_env=='development' and self.settings.allow_lan_http)
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
            repo.print_ready.ensure(db, share_id, paths)
        result = repo.operation(sid,owner,operation_key,{'action':'finalize','composite_id':composite_id},mutate)
        if result.get('share') and not result['share']['print_ready']:
            repo.print_ready.backfill(result['share']['final_id'])
            with repo.db.connect() as db:
                result['share'] = self.metadata(db, composite_id)
        return result

    def lookup(self, token):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise HTTPException(404, 'Link ảnh không hợp lệ hoặc không còn hiệu lực.')
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.repository.db.connect() as db:
            row = db.execute('SELECT s.*,c.path,c.sha256,c.width,c.height FROM shares s JOIN composites c ON c.id=s.composite_id WHERE s.token_hash=?', (token_hash,)).fetchone()
            if row is None or row['revoked_at'] or (row['expires_at'] and datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc)):
                raise HTTPException(404, 'Link ảnh không hợp lệ hoặc không còn hiệu lực.')
            final_id = row['id']
        self.repository.print_ready.backfill(final_id)
        with self.repository.db.connect() as db:
            ready = db.execute('SELECT * FROM print_ready WHERE final_id=?', (final_id,)).fetchone()
            result = dict(row)
            result.update({k: ready[k] for k in ('path','sha256','width','height')})
            return result

    def file(self, row, qr=False):
        root = self.settings.storage_root.resolve()
        path = (root / row['qr_path' if qr else 'path']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(404, 'Ảnh không còn trong storage.')
        return path
