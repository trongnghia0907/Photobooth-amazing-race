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
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image
from fastapi import HTTPException
from .drive_client import DriveError
from .sharing import public_origin


class CloudPublisher:
    def __init__(self, repo):
        self.repo = repo
        self.origin = os.getenv('PHOTO_CLOUD_ORIGIN', '').rstrip('/')
        self.secret = os.getenv('PHOTO_CLOUD_PUBLISH_SECRET', '')
        self.blob_token = os.getenv('PHOTO_CLOUD_BLOB_TOKEN', '')
        self.thread = None
        self.stopping = threading.Event()
        self.work_available = threading.Event()

    @property
    def configured(self):
        try:
            return len(self.secret) >= 32 and bool(self.blob_token) and public_origin(self.origin) == self.origin
        except HTTPException:
            return False

    def wake(self):
        self.work_available.set()

    @staticmethod
    def enroll(db, composite_id, size):
        db.execute('INSERT INTO cloud_publications(composite_id,size_bytes,remote_started) VALUES (?,?,0)',
                   (composite_id, size))

    @staticmethod
    def set_approval(db, composite_id, approved):
        # Updating a historical approval deliberately cannot create a cloud job.
        db.execute('''UPDATE cloud_publications SET version=version+1, approved=?, next_attempt=0,
            attempts=0, last_error=NULL WHERE composite_id=? AND approved<>?''', (approved, composite_id, approved))

    def ready_url(self, row):
        if not row or not row['approved'] or row['synced_version'] != row['version']:
            return None
        if not row['expires_at'] or row['expires_at'] <= time.time():
            return None
        url = row['share_url']
        prefix = f"{self.origin}/p/{row['composite_id']}."
        if url and url.startswith(prefix) and re.fullmatch(r'[a-f0-9]{64}', url[len(prefix):]):
            return url

    def share(self, sid, owner):
        with self.repo.db.connect() as db:
            self.repo.authorize(db, sid, owner)
            if not self.configured:
                return {'state': 'local'}
            row = db.execute('''SELECT q.* FROM cloud_publications q JOIN session_finals f
                ON f.composite_id=q.composite_id WHERE f.session_id=? AND NOT EXISTS
                (SELECT 1 FROM shares s WHERE s.composite_id=q.composite_id AND s.revoked_at IS NOT NULL)''', (sid,)).fetchone()
            url = self.ready_url(row)
            local = self.repo.sharing.metadata(db, row['composite_id'], prepare_print=False) if url else None
        if not row or not row['approved']:
            return {'state': 'local'}
        if row['synced_version'] != row['version']:
            return {'state': 'pending', 'composite_id': row['composite_id']}
        if not url:
            return {'state': 'expired', 'composite_id': row['composite_id']}
        qr = self.repo.sharing.qr_bytes(url)
        if local and not local['print_ready']:
            self.repo.print_ready.prepare_async(local['final_id'])
        print_asset = {field: local[field] for field in ('final_id', 'image_url', 'download_url', 'print_ready_version')} if local and local['print_ready'] else None
        return {'state': 'ready', 'composite_id': row['composite_id'], 'share_url': url,
                'public_ready': True, 'expires_at': datetime.fromtimestamp(row['expires_at'], timezone.utc).isoformat(),
                'print_asset': print_asset,
                'qr_image_data': 'data:image/png;base64,' + base64.b64encode(qr).decode('ascii')}

    def upload(self, key, data, mime):
        helper = Path(__file__).resolve().parents[3] / 'cloud' / 'upload.mjs'
        env = {**os.environ, 'BLOB_READ_WRITE_TOKEN': self.blob_token}
        subprocess.run(['node', str(helper), key, mime], input=data, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90, check=True)

    def register(self, payload, *, method='POST'):
        request = Request(self.origin + '/api/publication', json.dumps(payload).encode(),
                          {'Authorization': 'Bearer ' + self.secret, 'Content-Type': 'application/json'},
                          method=method)
        # Do not follow a redirect with Host credentials.
        class RejectRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with build_opener(RejectRedirect).open(request, timeout=40) as response:
            return json.loads(response.read(4096))

    def request_deletion(self, sid, item):
        with self.repo.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            final = db.execute('''SELECT q.version,q.remote_started FROM session_finals f
                JOIN sessions s ON s.id=f.session_id AND s.status='completed' AND s.composite_id=f.composite_id
                LEFT JOIN cloud_publications q ON q.composite_id=f.composite_id
                WHERE f.session_id=? AND f.composite_id=?''', (sid, item)).fetchone()
            if final is None:
                raise HTTPException(404, 'Không tìm thấy ảnh đã hoàn tất.')
            # A pre-upgrade job with a nonzero version may already have uploaded
            # bytes, even if the Host never received a publication receipt.
            cloud_pending = bool(final['version'] and final['remote_started'] != 0)
            db.execute('INSERT OR IGNORE INTO photo_deletions(composite_id,cloud_pending) VALUES (?,?)',
                       (item, cloud_pending))
            db.execute('UPDATE event_display_photos SET approved=0,hidden_at=? WHERE composite_id=? AND approved=1',
                       (time.time(), item))
            db.execute("UPDATE shares SET revoked_at=datetime('now') WHERE composite_id=? AND revoked_at IS NULL",
                       (item,))
            db.execute('DELETE FROM cloud_publications WHERE composite_id=?', (item,))
            state = db.execute('SELECT completed FROM photo_deletions WHERE composite_id=?', (item,)).fetchone()
            db.execute('UPDATE photo_deletions SET next_attempt=0 WHERE composite_id=? AND completed=0', (item,))
            db.commit()
        self.wake()
        return {'state': 'deleted' if state['completed'] else 'pending'}

    def process_deletion(self):
        with self.repo.db.connect() as db:
            job = db.execute('''SELECT d.*, c.session_id,c.path FROM photo_deletions d
                JOIN composites c ON c.id=d.composite_id WHERE d.completed=0 AND d.next_attempt<=?
                ORDER BY d.next_attempt LIMIT 1''', (time.time(),)).fetchone()
        if not job:
            return False
        item = job['composite_id']
        errors = []
        if job['cloud_pending']:
            try:
                if not self.configured:
                    raise ValueError('Missing cloud configuration')
                if self.register({'id': item}, method='DELETE') != {'deleted': item}:
                    raise ValueError('Unverified cloud deletion')
                with self.repo.db.connect() as db:
                    db.execute('UPDATE photo_deletions SET cloud_pending=0 WHERE composite_id=?', (item,))
            except (OSError, ValueError):
                errors.append('Vercel / Neon')
        drive = self.repo.drive
        if drive.process_lock.acquire(blocking=False):
            try:
                with self.repo.db.connect() as db:
                    upload = db.execute('SELECT drive_file_id FROM drive_uploads WHERE composite_id=?', (item,)).fetchone()
                if upload:
                    if upload['drive_file_id']:
                        drive.client.delete_composite(upload['drive_file_id'], item)
                    with self.repo.db.connect() as db:
                        db.execute('DELETE FROM drive_uploads WHERE composite_id=?', (item,))
            except DriveError:
                errors.append('Google Drive')
            finally:
                drive.process_lock.release()
        else:
            errors.append('Google Drive')

        if not errors:
            try:
                root = self.repo.settings.storage_root.resolve()
                expected = f'composites/{job["session_id"]}/{item}.png'
                path = root / expected
                if Path(job['path']) != Path(expected) or path.resolve() != path:
                    raise ValueError('Unexpected final composite path')
                with drive.restore_lock:
                    path.unlink(missing_ok=True)
            except (OSError, ValueError):
                errors.append('Ảnh trên Host')
        with self.repo.db.connect() as db:
            db.execute('''UPDATE photo_deletions SET completed=?,next_attempt=?,last_error=?
                WHERE composite_id=?''',
                (not errors, time.time()+30 if errors else 0, ', '.join(errors) or None, item))
        return True

    def still_eligible(self, item, version):
        with self.repo.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT version FROM cloud_publications WHERE composite_id=?', (item,)).fetchone()
            if not current or current['version'] != version:
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
            job = db.execute('''SELECT q.*, c.path, c.sha256, c.width, c.height, c.session_id, f.confirmed_at
                FROM cloud_publications q JOIN composites c ON c.id=q.composite_id
                JOIN session_finals f ON f.composite_id=q.composite_id
                WHERE q.version>q.synced_version AND q.next_attempt<=?
                ORDER BY q.approved, q.next_attempt LIMIT 1''', (time.time(),)).fetchone()
        if job is None:
            return False
        item = job['composite_id']
        version = job['version']
        with self.repo.db.connect() as db:
            if not db.execute('UPDATE cloud_publications SET remote_started=1 WHERE composite_id=? AND version=?',
                              (item, version)).rowcount:
                return True
        payload = {'id': item, 'version': version, 'approved': bool(job['approved'])}
        thumb_size = None
        upload_ms = 0
        since_confirm_ms = (time.time() - datetime.fromisoformat(job['confirmed_at']).timestamp()) * 1000
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
                upload_started = time.perf_counter()
                self.upload(f'photos/{item}/{job["sha256"]}.png', data, 'image/png')
                self.upload(f'photos/{item}/{thumb_sha}.jpg', thumb, 'image/jpeg')
                upload_ms = (time.perf_counter() - upload_started) * 1000
                payload.update(sha=job['sha256'], size=len(data), width=job['width'], height=job['height'],
                               thumb_sha=thumb_sha, thumb_size=thumb_size)
                if not self.still_eligible(item,version):
                    return True
            stage = 'register'
            register_started = time.perf_counter()
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
            logging.getLogger(__name__).info(
                'cloud_publication id=%s approved=%s bytes=%s worker_since_confirm_ms=%.1f blob_upload_ms=%.1f '
                'catalog_ack_ms=%.1f share_since_confirm_ms=%.1f',
                item, bool(job['approved']), job['size_bytes'], since_confirm_ms, upload_ms,
                (time.perf_counter()-register_started)*1000,
                (time.time()-datetime.fromisoformat(job['confirmed_at']).timestamp())*1000)
        except (OSError, ValueError, subprocess.SubprocessError):
            delay = min(300, 5 * 2 ** min(6, job['attempts']))
            with self.repo.db.connect() as db:
                db.execute('''UPDATE cloud_publications SET attempts=attempts+1,next_attempt=?,last_error=?
                    WHERE composite_id=? AND version=?''', (time.time()+delay, stage, item, version))
            logging.getLogger(__name__).warning('cloud_publication pending id=%s stage=%s retry_seconds=%s', item, stage, delay)
        return True

    def start(self):
        def run():
            while not self.stopping.is_set():
                self.work_available.clear()
                try:
                    more = self.process_deletion() or (self.configured and self.process_one())
                except Exception:
                    logging.getLogger(__name__).exception('cloud publication worker failed')
                    more = False
                self.work_available.wait(0.1 if more else 3)

        self.thread = threading.Thread(target=run, daemon=True, name='photobooth-cloud-publication')
        self.thread.start()

    def stop(self):
        self.stopping.set()
        self.wake()
        if self.thread:
            self.thread.join(timeout=3)
