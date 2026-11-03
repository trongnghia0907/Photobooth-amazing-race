"""Durable, opt-in upload queue. Single OS worker; all destructive cleanup is explicit."""
import hashlib
import sqlite3
import threading
import time
import logging
from fastapi import HTTPException
from ..runtime_lock import RuntimeLock
from .drive_client import GoogleDriveClient,DriveError
from .images import atomic_write

class DriveStorage:
    def __init__(self,repo,client=None):
        self.repo=repo;self.client=client or GoogleDriveClient(repo.settings)
        self.stop_event=threading.Event();self.thread=None;self.lease=None
        self.process_lock=threading.Lock()
        self.last_result='Chưa kiểm tra OAuth/quyền Drive.';self.privacy_ok=False
    def queue(self,db,composite_id):
        if self.repo.settings.google_drive_enabled:
            db.execute('INSERT OR IGNORE INTO drive_uploads(composite_id) VALUES (?)',(composite_id,))
    def status(self):
        with self.repo.db.connect() as db:
            rows=db.execute('SELECT state,COUNT(*) AS n FROM drive_uploads GROUP BY state').fetchall()
            errors=[dict(row) for row in db.execute('SELECT state,attempts,error FROM drive_uploads WHERE error IS NOT NULL ORDER BY next_attempt DESC LIMIT 10')]
            paths=[row[0] for row in db.execute('SELECT c.path FROM composites c JOIN drive_uploads u ON u.composite_id=c.id')]
        root=self.repo.settings.storage_root.resolve()
        size=sum((root/path).stat().st_size for path in paths if (root/path).is_file())
        return {'enabled':self.repo.settings.google_drive_enabled,'folder_id':self.repo.settings.google_drive_folder_id,
                'privacy_verified':self.privacy_ok,'last_result':self.last_result,'counts':{row['state']:row['n'] for row in rows},
                'privacy_audit':getattr(self.client,'last_privacy_audit',None),
                'staging_bytes':size,'errors':errors}
    def check(self):
        try:
            result=self.client.privacy();self.privacy_ok=True;self.last_result='OAuth và quyền Restricted đã được xác minh.';return result
        except Exception as error:
            self.privacy_ok=False;self.last_result=str(error) if isinstance(error,DriveError) else 'Không xác minh được Drive; upload bị chặn.'
            raise DriveError(self.last_result)
    def ready(self,composite_id):
        with self.repo.db.connect() as db:
            row=db.execute('SELECT * FROM drive_uploads WHERE composite_id=?',(composite_id,)).fetchone()
        return row is None or row['state']=='SYNCED'
    def process_one(self):
        if not self.process_lock.acquire(blocking=False):return False
        try:return self._process_one()
        finally:self.process_lock.release()
    def _process_one(self):
        with self.repo.db.connect() as db:
            row=db.execute("""SELECT u.*,c.path,c.sha256 FROM drive_uploads u JOIN composites c ON c.id=u.composite_id
                WHERE u.state!='SYNCED' AND u.next_attempt<=? ORDER BY u.next_attempt LIMIT 1""",(time.time(),)).fetchone()
        if not row:return False
        cid=row['composite_id']
        started=time.perf_counter()
        try:
            self.check() # Fail closed before every attempted upload, including retries.
            logging.getLogger(__name__).info('drive_privacy_ms=%.1f',(time.perf_counter()-started)*1000)
            path=(self.repo.settings.storage_root/row['path']).resolve()
            if not path.is_relative_to(self.repo.settings.storage_root.resolve()) or not path.is_file():raise DriveError('Staged composite bị mất. Không upload hoặc xóa dữ liệu.')
            data=path.read_bytes()
            if hashlib.sha256(data).hexdigest()!=row['sha256']:raise DriveError('Checksum staging không khớp; giữ file để Host kiểm tra.')
            file_id=row['drive_file_id'] or self.client.reserve_id()
            with self.repo.db.connect() as db:
                db.execute("UPDATE drive_uploads SET drive_file_id=?,state='UPLOADING' WHERE composite_id=?",(file_id,cid))
            upload_started=time.perf_counter()
            metadata=self.client.upload(file_id,path,cid)
            logging.getLogger(__name__).info('drive_upload_ms=%.1f',(time.perf_counter()-upload_started)*1000)
            verify_started=time.perf_counter()
            expected=hashlib.md5(data).hexdigest()
            if not metadata or metadata.get('id')!=file_id or metadata.get('md5Checksum')!=expected or int(metadata.get('size',-1))!=len(data) or metadata.get('parents')!=[self.repo.settings.google_drive_folder_id] or metadata.get('trashed'):
                raise DriveError('Không xác minh được metadata/checksum/file đích; giữ staging.')
            permissions=self.client.permissions(file_id)
            if not GoogleDriveClient.restricted_permissions({'mimeType':'image/png'},permissions):raise DriveError('File upload có quyền rộng hoặc chưa xác minh ACL; không phát QR, giữ staging và báo Host.')
            with self.repo.db.connect() as db:
                db.execute("UPDATE drive_uploads SET state='SYNCED',error=NULL,verified_at=datetime('now'),md5=? WHERE composite_id=?",(expected,cid))
            self.last_result='Đã upload và xác minh checksum composite.'
            logging.getLogger(__name__).info('drive_verification_ms=%.1f drive_total_ms=%.1f',(time.perf_counter()-verify_started)*1000,(time.perf_counter()-started)*1000)
        except Exception as error:
            message=str(error) if isinstance(error,DriveError) else 'Drive upload lỗi; dữ liệu staging vẫn được giữ.'
            self.last_result=message
            delay=min(300,2**min(row['attempts']+1,8))
            with self.repo.db.connect() as db:
                db.execute("UPDATE drive_uploads SET state='FAILED',attempts=attempts+1,next_attempt=?,error=? WHERE composite_id=?",(time.time()+delay,message,cid))
        return True
    def local(self,composite_id):
        with self.repo.db.connect() as db:
            row=db.execute('SELECT c.path,c.sha256,u.state,u.drive_file_id FROM composites c JOIN drive_uploads u ON u.composite_id=c.id WHERE c.id=?',(composite_id,)).fetchone()
        if not row:return None
        if row['state']!='SYNCED':raise HTTPException(503,'Ảnh đã lưu an toàn; đang chờ đồng bộ Google Drive.',headers={'Retry-After':'5'})
        path=(self.repo.settings.storage_root/row['path']).resolve()
        if not path.is_relative_to(self.repo.settings.storage_root.resolve()):raise HTTPException(404)
        try:
            self.check()
            permissions=self.client.permissions(row['drive_file_id'])
            if not GoogleDriveClient.restricted_permissions({'mimeType':'image/png'},permissions):raise DriveError('File không còn private.')
            data=self.client.download(row['drive_file_id'])
            if hashlib.sha256(data).hexdigest()!=row['sha256']:raise DriveError('Checksum Drive download không khớp.')
            # Verified private retrieval, cached for existing image/printing APIs.
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:atomic_write(path,data)
            return data
        except DriveError:raise HTTPException(503,'Ảnh tạm thời chưa truy cập được từ Drive. Hãy thử lại.',headers={'Retry-After':'5'}) from None
    def retry(self):
        with self.repo.db.connect() as db:db.execute("UPDATE drive_uploads SET state='PENDING',next_attempt=0 WHERE state='FAILED'")
    def evict(self,composite_id):
        """Explicit Host cache cleanup only; never applies to historical local finals."""
        self.check()
        # Verify a fresh private download before considering removal.
        self.local(composite_id)
        with self.repo.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("""SELECT c.path,c.sha256,c.session_id,u.state FROM drive_uploads u
                JOIN composites c ON c.id=u.composite_id WHERE c.id=?""",(composite_id,)).fetchone()
            if not row or row['state']!='SYNCED':raise DriveError('Chỉ dọn cache của composite đã SYNCED.')
            if db.execute("SELECT 1 FROM print_jobs WHERE session_id=? AND status IN ('queued','processing','failed')",(row['session_id'],)).fetchone():
                raise DriveError('Còn job in đang chờ/xử lý/lỗi. Giữ cache.')
            if db.execute("SELECT 1 FROM event_display_photos WHERE session_id=? AND approved=1",(row['session_id'],)).fetchone():
                raise DriveError('Ảnh đang trình chiếu; giữ cache để Event Gallery hoạt động ổn định.')
            candidate=self.repo.settings.storage_root/row['path'];path=candidate.resolve()
            if candidate!=path or not path.is_relative_to(self.repo.settings.storage_root.resolve()):raise DriveError('Đường dẫn cache không an toàn.')
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise DriveError('Cache không toàn vẹn; không xóa.')
            path.unlink(missing_ok=True);db.commit()
    def test_upload(self):
        from io import BytesIO
        from PIL import Image
        self.check()
        path=self.repo.settings.storage_root/'.drive-test.png'
        if not path.exists():
            output=BytesIO();Image.new('RGB',(64,64),'#2458d3').save(output,'PNG');atomic_write(path,output.getvalue())
        with self.repo.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT value FROM host_settings WHERE key='drive:test-id'").fetchone()
            file_id=row['value'] if row else self.client.reserve_id()
            db.execute("INSERT OR IGNORE INTO host_settings VALUES ('drive:test-id',?)",(file_id,));db.commit()
        metadata=self.client.upload(file_id,path,'DISPOSABLE-TEST')
        permissions=self.client.permissions(file_id)
        if not metadata or metadata.get('md5Checksum')!=hashlib.md5(path.read_bytes()).hexdigest() or metadata.get('parents')!=[self.repo.settings.google_drive_folder_id] or not GoogleDriveClient.restricted_permissions({'mimeType':'image/png'},permissions):
            raise DriveError('Upload test chưa xác minh được. Không dùng ảnh khách.')
        self.last_result='Test image private đã upload và xác minh checksum. Không dùng ảnh khách.'
        return self.status()
    def start(self):
        if not self.repo.settings.google_drive_enabled:return
        self.lease=RuntimeLock(self.repo.settings.storage_root/'.drive-worker.lock').acquire()
        # UPLOADING after a crash is reconciled by the same reserved Drive ID.
        with self.repo.db.connect() as db:db.execute("UPDATE drive_uploads SET state='PENDING' WHERE state='UPLOADING'")
        def run():
            while not self.stop_event.is_set():
                try:self.process_one()
                except (OSError,sqlite3.Error):pass
                self.stop_event.wait(2)
        self.thread=threading.Thread(target=run,daemon=True,name='photobooth-drive-sync');self.thread.start()
    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(50)
        if self.lease and (not self.thread or not self.thread.is_alive()):self.lease.close()
