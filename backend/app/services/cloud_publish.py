"""Durable publication of newly confirmed, approved composites only."""
import hashlib
from datetime import datetime, timezone
import base64
from io import BytesIO
import json
import logging
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image


class CloudPublisher:
    def __init__(self, repo):
        self.repo = repo
        self.origin = os.getenv('PHOTO_CLOUD_ORIGIN', '').rstrip('/')
        self.secret = os.getenv('PHOTO_CLOUD_PUBLISH_SECRET', '')
        self.blob_token = os.getenv('PHOTO_CLOUD_BLOB_TOKEN', '')
        self.thread = None
        self.stopping = threading.Event()

    @property
    def configured(self):
        try:
            url = urlsplit(self.origin)
            return (url.scheme == 'https' and bool(url.hostname) and not url.username
                    and not url.password and not (url.path or url.query or url.fragment)
                    and len(self.secret) >= 32 and bool(self.blob_token))
        except ValueError:
            return False

    @staticmethod
    def enroll(db, composite_id, size):
        db.execute('INSERT INTO cloud_publications(composite_id,size_bytes) VALUES (?,?)', (composite_id, size))

    @staticmethod
    def set_approval(db, composite_id, approved):
        # Updating a historical approval deliberately cannot create a cloud job.
        db.execute('''UPDATE cloud_publications SET version=version+1, approved=?, next_attempt=0,
            attempts=0, last_error=NULL WHERE composite_id=? AND approved<>?''', (approved, composite_id, approved))

    def share(self, sid, owner):
        with self.repo.db.connect() as db:
            self.repo.authorize(db, sid, owner)
            if not self.configured:
                return {'state': 'local'}
            row = db.execute('''SELECT q.* FROM cloud_publications q JOIN session_finals f
                ON f.composite_id=q.composite_id WHERE f.session_id=?''', (sid,)).fetchone()
        if not row or not row['approved']:
            return {'state': 'local'}
        if row['synced_version'] != row['version']:
            return {'state': 'pending', 'composite_id': row['composite_id']}
        if not row['expires_at'] or row['expires_at'] <= time.time():
            return {'state': 'expired', 'composite_id': row['composite_id']}
        return {'state': 'ready', 'composite_id': row['composite_id'], 'share_url': row['share_url'],
                'public_ready': True, 'expires_at': datetime.fromtimestamp(row['expires_at'], timezone.utc).isoformat(),
                'qr_image_data': 'data:image/png;base64,' + base64.b64encode(
                    self.repo.sharing.qr_bytes(row['share_url'])).decode('ascii')}

    def upload(self, key, data, mime):
        helper = Path(__file__).resolve().parents[3] / 'cloud' / 'upload.mjs'
        env = {**os.environ, 'BLOB_READ_WRITE_TOKEN': self.blob_token}
        subprocess.run(['node', str(helper), key, mime], input=data, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90, check=True)

    def register(self, payload):
        request = Request(self.origin + '/api/publication', json.dumps(payload).encode(),
                          {'Authorization': 'Bearer ' + self.secret, 'Content-Type': 'application/json'})
        # Do not follow a redirect with Host credentials.
        class RejectRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with build_opener(RejectRedirect).open(request, timeout=40) as response:
            return json.loads(response.read(4096))

    def still_eligible(self, item, version):
        with self.repo.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT version FROM cloud_publications WHERE composite_id=?', (item,)).fetchone()
            if current['version'] != version:
                return False
            row = db.execute('''SELECT 1 FROM event_display_photos e
                JOIN session_finals f ON f.composite_id=e.composite_id AND f.session_id=e.session_id
                JOIN sessions s ON s.id=f.session_id AND s.status='completed' AND s.composite_id=f.composite_id
                WHERE e.composite_id=? AND e.approved=1 AND e.hidden_at IS NULL
                AND NOT EXISTS(SELECT 1 FROM shares h WHERE h.composite_id=e.composite_id AND h.revoked_at IS NOT NULL)''', (item,)).fetchone()
            if not row:
                self.set_approval(db,item,False)
                db.commit()
            return bool(row)

    def process_one(self):
        with self.repo.db.connect() as db:
            job = db.execute('''SELECT q.*, c.path, c.sha256, c.width, c.height, c.session_id
                FROM cloud_publications q JOIN composites c ON c.id=q.composite_id
                WHERE q.version>q.synced_version AND q.next_attempt<=?
                ORDER BY q.approved, q.next_attempt LIMIT 1''', (time.time(),)).fetchone()
        if job is None:
            return False
        item = job['composite_id']
        version = job['version']
        payload = {'id': item, 'version': version, 'approved': bool(job['approved'])}
        thumb_size = None
        stage = 'upload'
        try:
            if job['approved']:
                if not self.still_eligible(item,version):
                    return True
                path = (self.repo.settings.storage_root / job['path']).resolve()
                if not path.is_relative_to(self.repo.settings.storage_root.resolve() / 'composites'):
                    raise ValueError('Invalid composite path')
                data = path.read_bytes()
                if len(data) != job['size_bytes'] or hashlib.sha256(data).hexdigest() != job['sha256']:
                    raise ValueError('Final composite failed checksum')
                with Image.open(BytesIO(data)) as image:
                    if image.format != 'PNG' or image.size != (job['width'], job['height']):
                        raise ValueError('Invalid final composite')
                    image.thumbnail((600, 600))
                    output = BytesIO()
                    image.convert('RGB').save(output, 'JPEG', quality=82)
                thumb = output.getvalue()
                thumb_size = len(thumb)
                thumb_sha = hashlib.sha256(thumb).hexdigest()
                self.upload(f'photos/{item}/{job["sha256"]}.png', data, 'image/png')
                self.upload(f'photos/{item}/{thumb_sha}.jpg', thumb, 'image/jpeg')
                payload.update(sha=job['sha256'], size=len(data), width=job['width'], height=job['height'],
                               thumb_sha=thumb_sha, thumb_size=thumb_size)
                if not self.still_eligible(item,version):
                    return True
            stage = 'register'
            result = self.register(payload)
            if not isinstance(result,dict):
                raise ValueError('Invalid catalog response')
            share_path = result.get('share_path')
            expires = result.get('expires_at')
            if result.get('version') != version or (job['approved'] and not (
                isinstance(share_path, str) and re.fullmatch(r'/p/'+re.escape(item)+r'\.[a-f0-9]{64}', share_path)
                and type(expires) in (int,float) and math.isfinite(expires) and 0 < expires < 4102444800
            )):
                raise ValueError('Unverified catalog response')
            with self.repo.db.connect() as db:
                db.execute('''UPDATE cloud_publications SET synced_version=version, attempts=0, next_attempt=0,
                    share_url=?,expires_at=?,thumbnail_bytes=COALESCE(?,thumbnail_bytes),last_error=NULL
                    WHERE composite_id=? AND version=?''',
                    (self.origin + share_path if job['approved'] else None, expires, thumb_size, item, version))
            logging.getLogger(__name__).info('cloud_publication confirmed id=%s bytes=%s thumbnail=%s approved=%s',
                                             item, job['size_bytes'], thumb_size, bool(job['approved']))
        except (OSError, ValueError, subprocess.SubprocessError):
            delay = min(300, 5 * 2 ** min(6, job['attempts']))
            with self.repo.db.connect() as db:
                db.execute('''UPDATE cloud_publications SET attempts=attempts+1,next_attempt=?,last_error=?
                    WHERE composite_id=? AND version=?''', (time.time()+delay, stage, item, version))
            logging.getLogger(__name__).warning('cloud_publication pending id=%s stage=%s retry_seconds=%s', item, stage, delay)
        return True

    def start(self):
        if not self.configured:
            return

        def run():
            while not self.stopping.is_set():
                try:
                    more = self.process_one()
                except Exception:
                    logging.getLogger(__name__).exception('cloud publication worker failed')
                    more = False
                self.stopping.wait(0.1 if more else 3)

        self.thread = threading.Thread(target=run, daemon=True, name='photobooth-cloud-publication')
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=3)
