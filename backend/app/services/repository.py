"""SQLite metadata + atomic files, with per-session idempotent mutations.

Files are immutable revisions. The slots table identifies current photos; old
revisions stay private for a later retention policy. A completed Phase 2 session
is sealed after confirmation. Originals are temporary; final/print-ready stay immutable.
"""
import hashlib
import hmac
import json
import sqlite3
import shutil
import uuid
import logging
import time
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
        from .print_ready import PrintReadyService
        self.print_ready = PrintReadyService(self)
        from .temporary_assets import TemporaryAssets
        self.temporary_assets = TemporaryAssets(self)
        from .drive_storage import DriveStorage
        self.drive = DriveStorage(self)

    def ensure_disk_space(self, extra_bytes=0):
        if shutil.disk_usage(self.settings.storage_root).free < self.settings.min_free_space_mb*1024*1024+extra_bytes:
            raise HTTPException(507,'Dung lượng lưu ảnh sắp hết. Nhờ Host giải phóng ổ đĩa; ảnh đã lưu vẫn được giữ.')

    def require_working(self, session):
        with self.db.connect() as db:
            pinned=db.execute('SELECT 1 FROM session_finals WHERE session_id=?',(session['id'],)).fetchone()
        if pinned or session['status']=='completed':
            raise HTTPException(409, 'Phiên đã chốt một ảnh cuối. Hãy bắt đầu khách mới để chụp/chỉnh ảnh khác.')

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
        final = db.execute('SELECT cleanup_status FROM session_finals WHERE session_id=?',(sid,)).fetchone()
        result['finalized'] = bool(final)
        result['cleanup_status'] = final['cleanup_status'] if final else 'working'
        share = self.sharing.metadata(db, row['composite_id']) if row['composite_id'] else None
        if share:
            result['share'] = share
        return result

    def get(self, sid, token, *, prepare_print=True):
        with self.db.connect() as db:
            db.execute('BEGIN')
            self.authorize(db, sid, token)
            result = self.snapshot(db, sid)
            db.commit()
            # The snapshot uses a read transaction. Generate/refresh a derived
            # footer only after that transaction ends (e.g. tunnel URL changed).
            share=result.get('share')
            if prepare_print and share and not share.get('print_ready'):
                self.print_ready.backfill(share['final_id'])
                result['share']=self.sharing.metadata(db,result['composite']['id'])
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

    def update_layout(self, sid, token, key, payload):
        def mutate(db, session, paths):
            # Historical captures also lock the layout after a retake/reset.
            if session['status'] != 'created' or db.execute(
                'SELECT 1 FROM photos WHERE session_id=? UNION ALL SELECT 1 FROM camera_captures WHERE session_id=? LIMIT 1',
                (sid, sid)).fetchone() or db.execute('SELECT 1 FROM session_finals WHERE session_id=?', (sid,)).fetchone():
                raise HTTPException(409, 'Chỉ đổi bố cục trước lần chụp đầu tiên. Hãy bắt đầu phiên mới.')
            db.execute('UPDATE sessions SET layout=?,slot_count=?,updated_at=? WHERE id=?',
                       (payload['layout'], payload['slot_count'], now(), sid))
        return self.operation(sid, token, key, {'action':'layout', **payload}, mutate)

    def write_image(self, folder, sid, image_id, image, created_paths):
        self.ensure_disk_space(len(image.data))
        relative = f'{folder}/{sid}/{image_id}.png'
        path = self.settings.storage_root / relative
        atomic_write(path, image.data)
        created_paths.append(path)
        return relative

    def upload_photo(self, sid, token, key, slot, source, image: ValidatedImage, expected_revision=None, capture_id=None):
        if self.settings.operation_mode=='event' and (source!='camera_original' or not capture_id):
            raise HTTPException(403,'Chế độ Event chỉ nhận JPG gốc từ camera đã xác minh; không nhận ảnh demo/upload.')
        def mutate(db, session, paths):
            self.require_working(session)
            if expected_revision is not None and session['shots_revision'] != expected_revision:
                raise HTTPException(409, 'Session đã thay đổi khi camera truyền ảnh. File camera được giữ riêng; không ghi đè slot mới.')
            if not 0 <= slot < session['slot_count']:
                raise HTTPException(422, 'Slot nằm ngoài session')
            photo_id = str(uuid.uuid4())
            revision = db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM photos WHERE session_id=? AND slot_index=?', (sid, slot)).fetchone()[0]
            path = self.write_image('originals', sid, photo_id, image, paths)
            db.execute('INSERT INTO photos VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (photo_id, sid, slot, revision, source, path, image.sha256, image.width, image.height, now()))
            if capture_id:
                db.execute("UPDATE camera_captures SET status='captured',photo_id=?,error_code=NULL,error_message=NULL,updated_at=? WHERE id=? AND session_id=?",(photo_id,now(),capture_id,sid))
            db.execute('INSERT INTO slots VALUES (?,?,?) ON CONFLICT(session_id,slot_index) DO UPDATE SET photo_id=excluded.photo_id', (sid, slot, photo_id))
            count = db.execute('SELECT COUNT(*) FROM slots WHERE session_id=?', (sid,)).fetchone()[0]
            db.execute('UPDATE sessions SET status=?,shots_revision=shots_revision+1,composite_id=NULL,updated_at=? WHERE id=?',
                       ('editing' if count == session['slot_count'] else 'capturing', now(), sid))
        return self.operation(sid, token, key, {'action': 'photo', 'slot': slot, 'source': source, 'input_hash': image.input_hash}, mutate)

    def delete_photos(self, sid, token, key, slot=None):
        def mutate(db, session, paths):
            self.require_working(session)
            if slot is not None and not 0 <= slot < session['slot_count']:
                raise HTTPException(422, 'Slot nằm ngoài session')
            if slot is None:
                db.execute('DELETE FROM slots WHERE session_id=?', (sid,))
            else:
                db.execute('DELETE FROM slots WHERE session_id=? AND slot_index=?', (sid, slot))
            db.execute("UPDATE sessions SET status='capturing',shots_revision=shots_revision+1,composite_id=NULL,updated_at=? WHERE id=?", (now(), sid))
        return self.operation(sid, token, key, {'action': 'delete', 'slot': slot}, mutate)

    def upload_composite(self, sid, token, key, shots_revision, editor, image):
        started=time.perf_counter()
        def mutate(db, session, paths):
            self.require_working(session)
            count = db.execute('SELECT COUNT(*) FROM slots WHERE session_id=?', (sid,)).fetchone()[0]
            if count != session['slot_count'] or session['shots_revision'] != shots_revision:
                raise HTTPException(409, 'Ảnh chụp đã thay đổi hoặc chưa đủ ảnh; hãy lưu lại các slot')
            image_id = str(uuid.uuid4())
            revision = db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM composites WHERE session_id=?', (sid,)).fetchone()[0]
            path = self.write_image('composites', sid, image_id, image, paths)
            db.execute('INSERT INTO composites VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (image_id, sid, revision, shots_revision, path, image.sha256, image.width, image.height, canonical(editor), now()))
            db.execute("UPDATE sessions SET composite_id=?,status='editing',updated_at=? WHERE id=?", (image_id, now(), sid))
        result=self.operation(sid, token, key, {'action': 'composite', 'shots_revision': shots_revision, 'editor': editor, 'input_hash': image.input_hash}, mutate)
        logging.getLogger(__name__).info('composite_durable_ms=%.1f',(time.perf_counter()-started)*1000)
        return result

    def complete(self, sid, token, key, composite_id):
        started=time.perf_counter()
        with self.db.connect() as db:
            self.authorize(db,sid,token)
            official=db.execute('SELECT composite_id FROM session_finals WHERE session_id=?',(sid,)).fetchone()
            if official and official['composite_id']!=composite_id:
                raise HTTPException(409,'Phiên đã có composite cuối khác; không thay đổi ảnh đã chốt.')
        def mutate(db, session, paths):
            pinned = db.execute('SELECT composite_id FROM session_finals WHERE session_id=?',(sid,)).fetchone()
            if pinned:
                if pinned['composite_id']!=composite_id:raise HTTPException(409,'Phiên đã có ảnh cuối khác.')
                try:self.temporary_assets.check_final(db,sid)
                except ValueError:raise HTTPException(503,'File composite cuối bị mất/thay đổi; cần khôi phục storage.') from None
                return
            if db.execute("SELECT 1 FROM camera_captures WHERE session_id=? AND (status IN ('capturing','transferring') OR (status='failed' AND uncertain=1))",(sid,)).fetchone():
                raise HTTPException(409,'Camera còn yêu cầu chụp/truyền chưa xác định. Hoàn tất xử lý trước khi chốt ảnh.')
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
            final_path = (self.settings.storage_root/composite['path']).resolve()
            if not final_path.is_relative_to(self.settings.storage_root.resolve()) or hashlib.sha256(final_path.read_bytes()).hexdigest()!=composite['sha256']:
                raise StoredFileMissing()
            db.execute("UPDATE sessions SET status='completed',updated_at=? WHERE id=?", (now(), sid))
            db.execute('INSERT INTO session_finals(session_id,composite_id,confirmed_at) VALUES (?,?,?)',(sid,composite_id,now()))
            self.temporary_assets.queue(db,sid,composite_id)
            self.drive.queue(db,composite_id)
            # Host policy AND this final snapshot's explicit guest consent.
            # Run once in the durable completion transaction; retries must not
            # undo a subsequent Host hide/revocation.
            if self.settings.event_gallery_auto_publish and json.loads(composite['editor_json']).get('event_display_consent') is True:
                import time
                db.execute('''INSERT OR IGNORE INTO event_display_photos
                    VALUES (?,?,?,?,?,?,?,NULL)''',
                    (sid,composite_id,str(uuid.uuid4()),1,'guest_consent','guest-consent:auto',time.time()))
        try:
            result = self.operation(sid, token, key, {'action': 'complete', 'composite_id': composite_id}, mutate)
            logging.getLogger(__name__).info('completion_and_durable_upload_job_ms=%.1f',(time.perf_counter()-started)*1000)
            try:self.temporary_assets.process_session(sid)
            except (OSError,sqlite3.Error):pass
            with self.db.connect() as db:
                result['cleanup_status'] = db.execute('SELECT cleanup_status FROM session_finals WHERE session_id=?',(sid,)).fetchone()[0]
            result['finalized'] = True
            return result
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
            session = self.authorize(db, sid, token)
            if session['status']=='completed' and (kind=='photos' or session['composite_id']!=image_id):
                raise HTTPException(410,'Phiên đã chốt. Chỉ ảnh composite cuối được giữ để xem/tải.')
            row = db.execute(f'SELECT path FROM {table} WHERE id=? AND session_id=?', (image_id, sid)).fetchone()
            if not row:
                raise HTTPException(404, 'Không tìm thấy ảnh')
            path = (self.settings.storage_root / row['path']).resolve()
            if kind=='composites' and not path.is_file():
                self.drive.local(image_id)
            if not path.is_relative_to(self.settings.storage_root.resolve()) or not path.is_file():
                raise HTTPException(404, 'Không tìm thấy ảnh')
            return path
