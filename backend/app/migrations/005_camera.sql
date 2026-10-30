-- Rebuild using SQLite's documented create/copy/drop/rename procedure.
-- Database runner disables foreign keys outside this transaction and checks
-- every FK before committing. Existing photo IDs/slots/files remain unchanged.
CREATE TABLE photos_v5 (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
 slot_index INTEGER NOT NULL, revision INTEGER NOT NULL,
 source TEXT NOT NULL CHECK(source IN ('demo','webcam_frame','manual_upload','camera_original')),
 path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
 width INTEGER NOT NULL,height INTEGER NOT NULL,created_at TEXT NOT NULL
);
INSERT INTO photos_v5 SELECT * FROM photos;
DROP TABLE photos;
ALTER TABLE photos_v5 RENAME TO photos;
CREATE INDEX photos_session ON photos(session_id,slot_index);
CREATE TABLE IF NOT EXISTS camera_captures (
 id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),
 request_key TEXT NOT NULL,slot_index INTEGER NOT NULL,expected_revision INTEGER NOT NULL,
 adapter_mode TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('capturing','transferring','transfer_failed','captured','failed')),
 adapter_reference TEXT,native_path TEXT,native_sha256 TEXT,mime TEXT,
 photo_id TEXT REFERENCES photos(id),error_code TEXT,error_message TEXT,uncertain INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(session_id,request_key)
);
PRAGMA user_version=5;
