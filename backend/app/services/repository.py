"""SQLite metadata + atomic files, with per-session idempotent mutations.

Files are immutable revisions. The slots table identifies current photos; old
revisions stay private for a later retention policy. A completed Phase 2 session
can be edited again (Phase 3 public-final immutability is not implemented).
"""
import hashlib
import hmac
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from ..config import Settings
from ..database import Database
from .images import ValidatedImage, atomic_write


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


class StoredFileMissing(HTTPException):
    def __init__(self):
        super().__init__(409, 'File đã lưu không còn trong storage; cần khôi phục hoặc chụp lại.')


class Repository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings.storage_root)
        from .sharing import SharingService
        self.sharing = SharingService(self)

    def authorize(self, db, session_id, token):
        row = db.execute('SELECT * FROM sessions WHERE id=?', (session_id,)).fetchone()
        if row is None or not hmac.compare_digest(row['owner_hash'], digest(token)):
            raise HTTPException(404, 'Không tìm thấy session hoặc không có quyền truy cập')
        return row

    def create(self, token, key, payload):
        payload = canonical(payload)
        create_key = digest(token + ':' + key)
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                existing = db.execute('SELECT * FROM sessions WHERE create_key=?', (create_key,)).fetchone()
                if existing:
                    if existing['create_payload'] != payload:
                        raise HTTPException(409, 'Idempotency-Key đã dùng cho dữ liệu khác')
                    result = self.snapshot(db, existing['id'])
                else:
                    values = json.loads(payload)
                    sid, stamp = str(uuid.uuid4()), now()
                    db.execute('INSERT INTO sessions (id,owner_hash,create_key,create_payload,layout,slot_count,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                               (sid, digest(token), create_key, payload, values['layout'], values['slot_count'], 'created', stamp, stamp))
                    result = self.snapshot(db, sid)
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise

    @staticmethod
    def photo_metadata(row):
        return {k: row[k] for k in ['id', 'slot_index', 'revision', 'source', 'sha256', 'width', 'height', 'created_at']}

    @staticmethod
    def composite_metadata(row):
        return {k: row[k] for k in ['id', 'revision', 'shots_revision', 'sha256', 'width', 'height', 'created_at']}

    def snapshot(self, db, sid):
        row = db.execute('SELECT * FROM sessions WHERE id=?', (sid,)).fetchone()
        photos = db.execute('SELECT p.* FROM slots s JOIN photos p ON p.id=s.photo_id WHERE s.session_id=? ORDER BY s.slot_index', (sid,)).fetchall()
        composite = db.execute('SELECT * FROM composites WHERE id=?', (row['composite_id'],)).fetchone()
        result = {
            'session_id': sid, 'status': row['status'], 'layout': row['layout'], 'slot_count': row['slot_count'],
            'shots_revision': row['shots_revision'], 'created_at': row['created_at'], 'updated_at': row['updated_at'],
            'photos': [self.photo_metadata(photo) for photo in photos],
            'composite': self.composite_metadata(composite) if composite else None,
        }
        share = self.sharing.metadata(db, row['composite_id']) if row['composite_id'] else None
        if share:
            result['share'] = share
        return result

    def get(self, sid, token):
        with self.db.connect() as db:
            db.execute('BEGIN')
            self.authorize(db, sid, token)
            result = self.snapshot(db, sid)
            db.commit()
            return result

    def operation(self, sid, token, key, payload, mutate):
        fingerprint = digest(canonical(payload))
        created_paths = []
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                session = self.authorize(db, sid, token)
                previous = db.execute('SELECT * FROM operations WHERE session_id=? AND operation_key=?', (sid, key)).fetchone()
                if previous:
                    if previous['payload_hash'] != fingerprint:
                        raise HTTPException(409, 'Idempotency-Key đã dùng cho dữ liệu khác')
                    result = json.loads(previous['result_json'])
                    shared_composite = result.pop('_share_composite', None)
                    if shared_composite:
                        share = self.sharing.metadata(db, shared_composite)
                        if share:
                            result['share'] = share
                else:
                    mutate(db, session, created_paths)
                    result = self.snapshot(db, sid)
                    cached = dict(result)
                    share = cached.pop('share', None)
                    if share:
                        cached['_share_composite'] = share['composite_id']
                    db.execute('INSERT INTO operations VALUES (?,?,?,?)', (sid, key, fingerprint, canonical(cached)))
                db.commit()
                return result
            except Exception:
                db.rollback()
                for path in created_paths:
                    path.unlink(missing_ok=True)
                raise

    def write_image(self, folder, sid, image_id, image, created_paths):
        relative = f'{folder}/{sid}/{image_id}.png'
        path = self.settings.storage_root / relative
        atomic_write(path, image.data)
        created_paths.append(path)
        return relative

    def upload_photo(self, sid, token, key, slot, source, image: ValidatedImage):
        def mutate(db, session, paths):
            if not 0 <= slot < session['slot_count']:
                raise HTTPException(422, 'Slot nằm ngoài session')
            photo_id = str(uuid.uuid4())
            revision = db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM photos WHERE session_id=? AND slot_index=?', (sid, slot)).fetchone()[0]
            path = self.write_image('originals', sid, photo_id, image, paths)
            db.execute('INSERT INTO photos VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (photo_id, sid, slot, revision, source, path, image.sha256, image.width, image.height, now()))
            db.execute('INSERT INTO slots VALUES (?,?,?) ON CONFLICT(session_id,slot_index) DO UPDATE SET photo_id=excluded.photo_id', (sid, slot, photo_id))
            count = db.execute('SELECT COUNT(*) FROM slots WHERE session_id=?', (sid,)).fetchone()[0]
            db.execute('UPDATE sessions SET status=?,shots_revision=shots_revision+1,composite_id=NULL,updated_at=? WHERE id=?',
                       ('editing' if count == session['slot_count'] else 'capturing', now(), sid))
        return self.operation(sid, token, key, {'action': 'photo', 'slot': slot, 'source': source, 'input_hash': image.input_hash}, mutate)

    def delete_photos(self, sid, token, key, slot=None):
        def mutate(db, session, paths):
            if slot is not None and not 0 <= slot < session['slot_count']:
                raise HTTPException(422, 'Slot nằm ngoài session')
            if slot is None:
                db.execute('DELETE FROM slots WHERE session_id=?', (sid,))
            else:
                db.execute('DELETE FROM slots WHERE session_id=? AND slot_index=?', (sid, slot))
            db.execute("UPDATE sessions SET status='capturing',shots_revision=shots_revision+1,composite_id=NULL,updated_at=? WHERE id=?", (now(), sid))
        return self.operation(sid, token, key, {'action': 'delete', 'slot': slot}, mutate)

    def upload_composite(self, sid, token, key, shots_revision, editor, image):
        def mutate(db, session, paths):
            count = db.execute('SELECT COUNT(*) FROM slots WHERE session_id=?', (sid,)).fetchone()[0]
            if count != session['slot_count'] or session['shots_revision'] != shots_revision:
                raise HTTPException(409, 'Ảnh chụp đã thay đổi hoặc chưa đủ ảnh; hãy lưu lại các slot')
            image_id = str(uuid.uuid4())
            revision = db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM composites WHERE session_id=?', (sid,)).fetchone()[0]
            path = self.write_image('composites', sid, image_id, image, paths)
            db.execute('INSERT INTO composites VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (image_id, sid, revision, shots_revision, path, image.sha256, image.width, image.height, canonical(editor), now()))
            db.execute("UPDATE sessions SET composite_id=?,status='editing',updated_at=? WHERE id=?", (image_id, now(), sid))
        return self.operation(sid, token, key, {'action': 'composite', 'shots_revision': shots_revision, 'editor': editor, 'input_hash': image.input_hash}, mutate)

    def complete(self, sid, token, key, composite_id):
        def mutate(db, session, paths):
            if session['composite_id'] != composite_id:
                raise HTTPException(409, 'Ảnh ghép chưa lưu hoặc đã thay đổi')
            composite = db.execute('SELECT * FROM composites WHERE id=? AND session_id=?', (composite_id, sid)).fetchone()
            if not composite or composite['shots_revision'] != session['shots_revision']:
                raise HTTPException(409, 'Ảnh ghép không còn khớp các slot')
            for row in db.execute('SELECT p.path FROM slots s JOIN photos p ON p.id=s.photo_id WHERE s.session_id=?', (sid,)):
                if not (self.settings.storage_root / row['path']).is_file():
                    raise StoredFileMissing()
            if not (self.settings.storage_root / composite['path']).is_file():
                raise StoredFileMissing()
            db.execute("UPDATE sessions SET status='completed',updated_at=? WHERE id=?", (now(), sid))
        try:
            return self.operation(sid, token, key, {'action': 'complete', 'composite_id': composite_id}, mutate)
        except StoredFileMissing:
            # A missing previously committed file is an integrity failure, unlike
            # a retryable upload error. Do not mark transient network errors failed.
            with self.db.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute("UPDATE sessions SET status='failed',updated_at=? WHERE id=? AND composite_id=?", (now(), sid, composite_id))
                db.commit()
            raise

    def image_path(self, sid, token, kind, image_id):
        table = 'photos' if kind == 'photos' else 'composites'
        with self.db.connect() as db:
            self.authorize(db, sid, token)
            row = db.execute(f'SELECT path FROM {table} WHERE id=? AND session_id=?', (image_id, sid)).fetchone()
            if not row:
                raise HTTPException(404, 'Không tìm thấy ảnh')
            path = (self.settings.storage_root / row['path']).resolve()
            if not path.is_relative_to(self.settings.storage_root.resolve()) or not path.is_file():
                raise HTTPException(404, 'Không tìm thấy ảnh')
            return path
