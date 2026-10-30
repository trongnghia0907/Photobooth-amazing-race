"""Durable, retryable cleanup of working files only after a sealed final commit.

Never glob/delete whole directories: every target comes from session metadata,
is allowlisted, resolved and checked within storage. Missing files are idempotent.
"""
import hashlib
from pathlib import PurePosixPath
import sqlite3
import threading
from uuid import UUID


class TemporaryAssets:
    def __init__(self, repository):
        self.repo = repository
        self.stop_event = threading.Event()
        self.thread = None

    def queue(self, db, sid, composite_id):
        paths = [r[0] for r in db.execute('SELECT path FROM photos WHERE session_id=?',(sid,))]
        for row in db.execute('SELECT id,native_path FROM camera_captures WHERE session_id=?',(sid,)):
            if row['native_path']:paths.append(row['native_path'])
            UUID(row['id'])
            paths.append(f"camera_spool/{row['id']}.jpg")
        paths += [r[0] for r in db.execute('''SELECT path FROM composites WHERE session_id=? AND id!=?
            AND NOT EXISTS(SELECT 1 FROM shares WHERE composite_id=composites.id)''',(sid,composite_id))]
        db.executemany('INSERT OR IGNORE INTO temporary_file_cleanup(session_id,path) VALUES (?,?)',[(sid,p) for p in paths])

    def target(self, db, sid, relative):
        UUID(sid)
        parts = PurePosixPath(relative).parts
        root = self.repo.settings.storage_root.resolve()
        if len(parts)==3 and parts[0] in ('originals','camera_originals','composites') and parts[1]==sid:
            UUID(PurePosixPath(parts[2]).stem)
        elif len(parts)==2 and parts[0]=='camera_spool':
            capture_id = str(UUID(PurePosixPath(parts[1]).stem))
            if not db.execute('SELECT 1 FROM camera_captures WHERE id=? AND session_id=?',(capture_id,sid)).fetchone():
                raise ValueError('Spool ownership mismatch')
        else:raise ValueError('Invalid temporary path')
        candidate = root/relative
        target = candidate.resolve()
        if target!=candidate or not target.is_relative_to(root) or target == root:
            raise ValueError('Temporary path outside storage')
        # No final/composite/share/QR/print input may ever enter the deletion queue.
        protected = db.execute('''SELECT 1 FROM composites c WHERE c.path=? AND
            (EXISTS(SELECT 1 FROM session_finals f WHERE f.composite_id=c.id)
             OR EXISTS(SELECT 1 FROM shares s WHERE s.composite_id=c.id))''',(relative,)).fetchone()
        if protected:raise ValueError('Protected final')
        return target

    def check_final(self, db, sid):
        row = db.execute('''SELECT c.path,c.sha256 FROM session_finals f JOIN sessions s ON s.id=f.session_id
            JOIN composites c ON c.id=f.composite_id WHERE f.session_id=? AND s.status='completed'
            AND s.composite_id=f.composite_id AND c.session_id=f.session_id''',(sid,)).fetchone()
        if not row:raise ValueError('Session has no durable final')
        root = self.repo.settings.storage_root.resolve();candidate = root/row['path'];path = candidate.resolve()
        if path!=candidate or not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('Final missing or corrupt; keep working files')

    def process_session(self, sid):
        with self.repo.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            final = db.execute('SELECT * FROM session_finals WHERE session_id=?',(sid,)).fetchone()
            if not final or final['cleanup_status'] in ('complete','retained_legacy'):return
            try:
                self.check_final(db,sid)
                if db.execute("SELECT 1 FROM camera_captures WHERE session_id=? AND status IN ('capturing','transferring')",(sid,)).fetchone():
                    raise ValueError('Camera still transferring')
                self.queue(db,sid,final['composite_id'])
                for row in db.execute("SELECT path FROM temporary_file_cleanup WHERE session_id=? AND status='pending'",(sid,)).fetchall():
                    self.check_final(db,sid)
                    self.target(db,sid,row['path']).unlink(missing_ok=True)
                    db.execute("UPDATE temporary_file_cleanup SET status='deleted' WHERE session_id=? AND path=?",(sid,row['path']))
                db.execute("UPDATE session_finals SET cleanup_status='complete',cleanup_error=NULL WHERE session_id=?",(sid,))
            except (OSError,ValueError):
                db.execute("UPDATE session_finals SET cleanup_status='blocked',cleanup_error=? WHERE session_id=?",
                           ('Chưa dọn hết ảnh tạm; giữ ảnh còn lại và tự thử lại sau. Kiểm tra file final/quyền ổ đĩa.',sid))
            db.commit()

    def process_pending(self):
        with self.repo.db.connect() as db:
            ids = [r[0] for r in db.execute("SELECT session_id FROM session_finals WHERE cleanup_status IN ('pending','blocked') ORDER BY CASE cleanup_status WHEN 'pending' THEN 0 ELSE 1 END,confirmed_at LIMIT 20")]
        for sid in ids:self.process_session(sid)

    def start(self):
        def run():
            while not self.stop_event.is_set():
                try:self.process_pending()
                except (OSError,sqlite3.Error):pass  # queue remains durable, no unsafe fallback deletion
                self.stop_event.wait(5)
        self.thread = threading.Thread(target=run,daemon=True,name='osa-working-file-cleanup');self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(5)
