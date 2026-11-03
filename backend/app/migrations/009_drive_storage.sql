CREATE TABLE IF NOT EXISTS drive_uploads (
    composite_id TEXT PRIMARY KEY REFERENCES composites(id),
    state TEXT NOT NULL DEFAULT 'PENDING' CHECK(state IN ('PENDING','UPLOADING','SYNCED','FAILED')),
    drive_file_id TEXT UNIQUE,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt REAL NOT NULL DEFAULT 0,
    error TEXT,
    verified_at TEXT,
    md5 TEXT
);
CREATE INDEX IF NOT EXISTS drive_upload_due ON drive_uploads(state,next_attempt);
PRAGMA user_version=9;
