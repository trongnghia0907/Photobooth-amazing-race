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
            if version > 3:
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
