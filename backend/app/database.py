from contextlib import contextmanager
from pathlib import Path
import sqlite3


class Database:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / 'photobooth.sqlite3'
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 9:
                raise RuntimeError('Database schema newer than this backend')
            if version == 0:
                migration = Path(__file__).parent / 'migrations/001_initial.sql'
                db.executescript('BEGIN IMMEDIATE;\n' + migration.read_text() + '\nCOMMIT;')
                version = 1
            if version == 1:
                migration = Path(__file__).parent / 'migrations/002_sharing.sql'
                db.executescript('BEGIN IMMEDIATE;\n' + migration.read_text() + '\nCOMMIT;')
                version = 2
            if version == 2:
                migration = Path(__file__).parent / 'migrations/003_share_ack_redaction.sql'
                db.executescript('BEGIN IMMEDIATE;\n' + migration.read_text() + '\nCOMMIT;')
                version = 3
            if version == 3:
                migration = Path(__file__).parent / 'migrations/004_printing.sql'
                db.executescript('BEGIN IMMEDIATE;\n' + migration.read_text() + '\nCOMMIT;')
                version = 4
            if version == 4:
                migration = Path(__file__).parent / 'migrations/005_camera.sql'
                db.execute('PRAGMA foreign_keys=OFF')
                try:
                    db.executescript('BEGIN IMMEDIATE;\n' + migration.read_text())
                    if db.execute('PRAGMA foreign_key_check').fetchone():
                        raise RuntimeError('Camera migration foreign key check failed')
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.execute('PRAGMA foreign_keys=ON')
                version = 5
            if version == 5:
                migration = Path(__file__).parent / 'migrations/006_storage_lifecycle.sql'
                db.executescript('BEGIN IMMEDIATE;\n' + migration.read_text() + '\nCOMMIT;')
                version = 6
            if version == 6:
                migration = Path(__file__).parent / 'migrations/007_deployment.sql'
                db.executescript('BEGIN IMMEDIATE;\n' + migration.read_text() + '\nCOMMIT;')
                version = 7
            if version == 7:
                migration = Path(__file__).parent / 'migrations/008_event_display.sql'
                db.executescript('BEGIN IMMEDIATE;\n' + migration.read_text() + '\nCOMMIT;')
                version = 8
            if version == 8:
                migration = Path(__file__).parent / 'migrations/009_drive_storage.sql'
                db.executescript('BEGIN IMMEDIATE;\n' + migration.read_text() + '\nCOMMIT;')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=10000')
        try:
            yield db
        finally:
            db.close()
