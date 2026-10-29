CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    owner_hash TEXT NOT NULL,
    create_key TEXT NOT NULL UNIQUE,
    create_payload TEXT NOT NULL,
    layout TEXT NOT NULL,
    slot_count INTEGER NOT NULL CHECK(slot_count IN (4, 6)),
    status TEXT NOT NULL CHECK(status IN ('created','capturing','editing','completed','failed')),
    shots_revision INTEGER NOT NULL DEFAULT 0,
    composite_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS photos (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    slot_index INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('demo','webcam_frame','manual_upload')),
    path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS slots (
    session_id TEXT NOT NULL REFERENCES sessions(id),
    slot_index INTEGER NOT NULL,
    photo_id TEXT NOT NULL REFERENCES photos(id),
    PRIMARY KEY (session_id, slot_index)
);
CREATE TABLE IF NOT EXISTS composites (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    revision INTEGER NOT NULL,
    shots_revision INTEGER NOT NULL,
    path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    editor_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations (
    session_id TEXT NOT NULL REFERENCES sessions(id),
    operation_key TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    result_json TEXT NOT NULL,
    PRIMARY KEY(session_id, operation_key)
);
CREATE INDEX IF NOT EXISTS photos_session ON photos(session_id, slot_index);
CREATE INDEX IF NOT EXISTS composites_session ON composites(session_id);
PRAGMA user_version = 1;
