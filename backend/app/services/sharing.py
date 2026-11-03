"""One durable, immutable public share per confirmed composite revision.

Token = HMAC-SHA256(secret file, random nonce + composite UUID). SQLite stores
the random nonce and token hash, never a plaintext bearer token. The separate
32-byte secret must be backed up with the database to reconstruct owner URLs.
"""
import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import time
import uuid
import logging
from datetime import datetime, timezone, timedelta
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
        self.public_checks={}
        self.settings = repository.settings
        self.key_file = self.settings.storage_root / '.share-key'

    def temporary_origin(self):
        """Local operator-owned Quick Tunnel override; ignored in Event/production."""
        if self.settings.app_env!='development' or self.settings.operation_mode not in ('development','rehearsal'):
            return None
        try:
            data=json.loads((self.settings.storage_root/'.mobile-qr-origin.json').read_text(encoding='utf-8'))
            origin=data['origin']
            if data.get('phase','ready')!='ready' or data['expires_at']<=time.time() or not re.fullmatch(r'https://[a-z0-9-]+\.trycloudflare\.com',origin):
                return None
            return origin
        except (OSError,ValueError,KeyError,TypeError):
            return None

    def tunnel_status(self):
        if self.settings.app_env!='development':return 'not_managed'
        try:
            data=json.loads((self.settings.storage_root/'.mobile-qr-origin.json').read_text(encoding='utf-8'))
            if data.get('phase')=='connecting':return 'connecting' if data.get('expires_at',0)>time.time() else 'disconnected'
            return 'ready' if self.temporary_origin() else 'disconnected'
        except (OSError,ValueError,TypeError):return 'not_managed'

    def origin(self):
        return self.temporary_origin() or public_origin(self.settings.public_base_url,
            allow_local=self.settings.app_env=='development',
            allow_lan=self.settings.app_env=='development' and self.settings.allow_lan_http)

    @staticmethod
    def qr_bytes(url):
        started=time.perf_counter()
        qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=10,border=4)
        qr.add_data(url);qr.make(fit=True)
        buffer=BytesIO();qr.make_image(fill_color='#1E40AF',back_color='white').save(buffer,format='PNG')
        result=buffer.getvalue()
        logging.getLogger(__name__).info('qr_image_ms=%.1f',(time.perf_counter()-started)*1000)
        return result

    def configuration(self):
        try:
            origin = self.origin()
            local = is_local_origin(origin)
            lan=is_lan_origin(origin)
            return {'configured': True, 'app_env': self.settings.app_env, 'base_url': origin, 'local_only': local,'lan_only':lan,
                    'temporary_origin_supported':self.settings.app_env=='development','temporary':bool(self.temporary_origin()),
                    'tunnel_status':self.tunnel_status(),
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
        base=self.temporary_origin() or row['public_base_url']
        if not db.in_transaction:self.repository.print_ready.backfill(row['id'])
        ready = self.repository.print_ready.current(db,row['id'])
        return {
            'final_id': row['id'], 'composite_id': row['composite_id'],
            'share_url': f"{base}/p/{token}",
            'qr_image_url': f'/p/{token}/qr.png', 'image_url': f'/p/{token}/image',
            'download_url': f'/p/{token}/download', 'qr_embedded': bool(ready),
            'print_ready_error':None if ready else 'Chờ URL HTTPS công khai hoạt động để tạo bản in có QR. Không in QR localhost.',
            'print_ready_version':ready['sha256'] if ready else None,
            'print_ready': {k: ready[k] for k in ('sha256','width','height','source_height','qr_x','qr_y','qr_size')} if ready else None,
            'local_only': is_local_origin(base),
            'lan_only': is_lan_origin(base),
            'temporary':bool(self.temporary_origin()),
            'public_ready':self.public_checks.get(f'{base}/p/{token}',0)>time.monotonic(),
            'expires_at':row['expires_at'],
        }

    def verify_public(self,sid,owner):
        """Bounded per-session HTTPS probe; never wait for cloud upload."""
        import httpx
        import logging
        started=time.perf_counter()
        state=self.repository.get(sid,owner);share=state.get('share')
        if not share:raise HTTPException(409,'Hãy xác nhận composite trước khi tạo QR.')
        if share['local_only'] or share['lan_only']:return share
        url=share['share_url']
        with self.repository.db.connect() as db:
            expected=db.execute('SELECT sha256 FROM composites WHERE id=?',(share['composite_id'],)).fetchone()[0]
        try:
            if self.public_checks.get(url,0)<=time.monotonic():
                with httpx.Client(timeout=3,trust_env=False,follow_redirects=False) as client:
                    response=client.get(url+'/status')
                data=response.json()
                if response.status_code!=200 or data.get('registered') is not True or data.get('fingerprint')!=expected:
                    raise ValueError('Gateway did not recognize the finalized session')
                # A short proof lease; failed/changed origins cannot reuse it.
                self.public_checks={k:v for k,v in self.public_checks.items() if v>time.monotonic()}
                self.public_checks[url]=time.monotonic()+8
            # First successful public issuance starts the UTC 24-hour period.
            # Keep existing deadlines and tokens; a refresh never renews them.
            with self.repository.db.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('UPDATE shares SET expires_at=? WHERE id=? AND expires_at IS NULL AND revoked_at IS NULL',
                    ((datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(),share['final_id']))
                row=db.execute('SELECT expires_at,revoked_at FROM shares WHERE id=?',(share['final_id'],)).fetchone()
                if not row or row['revoked_at'] or datetime.fromisoformat(row['expires_at'])<=datetime.now(timezone.utc):
                    raise HTTPException(404,'Mã QR đã hết hạn hoặc bị thu hồi.')
                db.commit()
            share['public_ready']=True;share['expires_at']=row['expires_at']
            logging.getLogger(__name__).info('public_gateway_registration_ms=%.1f',(time.perf_counter()-started)*1000)
            return share
        except (httpx.HTTPError,ValueError,KeyError):
            self.public_checks.pop(url,None)
            raise HTTPException(503,'Chưa xác nhận được trang ảnh HTTPS của phiên. Kiểm tra tunnel/gateway; hệ thống sẽ tự thử lại.') from None

    def finalize(self, sid, owner, operation_key, composite_id):
        started=time.perf_counter()
        repo = self.repository
        repo.get(sid,owner)
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
            repo.ensure_disk_space()
            base = self.origin()
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
        logging.getLogger(__name__).info('share_finalize_ms=%.1f',(time.perf_counter()-started)*1000)
        return result

    def lookup(self, token, metadata_only=False):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise HTTPException(404, 'Link ảnh không hợp lệ hoặc không còn hiệu lực.')
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.repository.db.connect() as db:
            row = db.execute('SELECT s.*,c.path,c.sha256,c.width,c.height FROM shares s JOIN composites c ON c.id=s.composite_id WHERE s.token_hash=?', (token_hash,)).fetchone()
            if row is None or row['revoked_at'] or (row['expires_at'] and datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc)):
                raise HTTPException(404, 'Link ảnh không hợp lệ hoặc không còn hiệu lực.')
            final_id = row['id']
        if metadata_only:return dict(row)
        # Token authorization remains mandatory. Prefer checksum-verified local
        # staging, independent of remote upload or its network latency.
        source=(self.settings.storage_root/row['path']).resolve()
        if not source.is_relative_to(self.settings.storage_root.resolve()):raise HTTPException(404)
        if not source.is_file():self.repository.drive.local(row['composite_id'])
        if not source.is_file():raise HTTPException(503,'Ảnh đang được xử lý. Hệ thống sẽ tự thử lại.')
        if hashlib.sha256(source.read_bytes()).hexdigest()!=row['sha256']:
            raise HTTPException(503,'Ảnh tạm thời chưa sẵn sàng. Hệ thống sẽ tự thử lại.')
        self.repository.print_ready.backfill(final_id)
        with self.repository.db.connect() as db:
            ready = self.repository.print_ready.current(db,final_id)
            result = dict(row)
            if ready is None:
                return result
            result.update({k: ready[k] for k in ('path','sha256','width','height')})
            return result

    def file(self, row, qr=False):
        root = self.settings.storage_root.resolve()
        path = (root / row['qr_path' if qr else 'path']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(404, 'Ảnh không còn trong storage.')
        return path
