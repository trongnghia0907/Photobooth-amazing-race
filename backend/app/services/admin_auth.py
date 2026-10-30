"""ENV credentials, PBKDF2 at rest, revocable HttpOnly sessions and CSRF."""
import hashlib
import hmac
import secrets
import threading
import time
from fastapi import HTTPException

COOKIE = 'osa_host'
COOKIE_PATH = '/api/admin'


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600_000).hex()


class AdminAuth:
    def __init__(self, repo):
        self.repo = repo
        self.settings = repo.settings
        self.attempts = {}
        self.lock = threading.Lock()
        self.enabled = bool(self.settings.admin_username and len(self.settings.admin_password) >= 12)
        with repo.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM admin_credentials WHERE id=1').fetchone()
            same = False
            if row and self.enabled:
                salt, old = row['password_hash'].split(':')
                same = row['username'] == self.settings.admin_username and hmac.compare_digest(old,password_hash(self.settings.admin_password,salt))
            if not same:
                db.execute('DELETE FROM admin_sessions')
                db.execute('DELETE FROM admin_credentials')
                if self.enabled:
                    salt = secrets.token_hex(16)
                    db.execute('INSERT INTO admin_credentials VALUES (1,?,?)',
                               (self.settings.admin_username,salt+':'+password_hash(self.settings.admin_password,salt)))
            db.commit()

    @staticmethod
    def csrf(token):
        return hmac.new(token.encode(),b'OSA host CSRF',hashlib.sha256).hexdigest()

    def login(self, username, password, ip):
        if not self.enabled:
            raise HTTPException(503, 'Host login chưa cấu hình. Đặt ADMIN_USERNAME và ADMIN_PASSWORD ít nhất 12 ký tự, rồi restart backend.')
        with self.lock:
            stamp = time.time()
            self.attempts = {k:[t for t in v if t > stamp-60] for k,v in self.attempts.items() if any(t > stamp-60 for t in v)}
            attempts = self.attempts.setdefault(ip,[])
            if len(attempts) >= 5:
                raise HTTPException(429,'Thử đăng nhập quá nhiều. Chờ một phút.')
            if len(self.attempts) > 1000:
                raise HTTPException(429,'Hãy thử lại sau.')
            attempts.append(stamp)
        with self.repo.db.connect() as db:
            row = db.execute('SELECT * FROM admin_credentials WHERE id=1').fetchone()
            salt, hashed = row['password_hash'].split(':')
            valid = hmac.compare_digest(password_hash(password,salt),hashed)
            if not valid or not hmac.compare_digest(username.encode(),row['username'].encode()):
                raise HTTPException(401,'Thông tin đăng nhập không đúng')
            with self.lock:self.attempts.pop(ip,None)
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM admin_sessions WHERE expires_at<?',(time.time(),))
            db.execute('INSERT INTO admin_sessions VALUES (?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(),row['password_hash'],time.time()+8*3600))
        return token

    def require(self, request, mutation=False):
        token = request.cookies.get(COOKIE,'')
        if not self.enabled or not token:
            raise HTTPException(401,'Host cần đăng nhập')
        with self.repo.db.connect() as db:
            row = db.execute('''SELECT s.* FROM admin_sessions s JOIN admin_credentials c
                ON c.password_hash=s.auth_tag WHERE s.token_hash=? AND s.expires_at>?''',
                (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        if not row:
            raise HTTPException(401,'Phiên đăng nhập hết hiệu lực')
        if mutation and not hmac.compare_digest(request.headers.get('X-CSRF-Token','').encode(),self.csrf(token).encode()):
            raise HTTPException(403,'Thiếu CSRF token hợp lệ')
        return token

    def logout(self, token):
        with self.repo.db.connect() as db:
            db.execute('DELETE FROM admin_sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
