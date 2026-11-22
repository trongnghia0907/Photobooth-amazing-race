CREATE TABLE IF NOT EXISTS cloud_publications (
 composite_id TEXT PRIMARY KEY REFERENCES composites(id),
 version INTEGER NOT NULL DEFAULT 0,
 approved INTEGER NOT NULL DEFAULT 0 CHECK(approved IN (0,1)),
 synced_version INTEGER NOT NULL DEFAULT 0,
 next_attempt REAL NOT NULL DEFAULT 0,
 attempts INTEGER NOT NULL DEFAULT 0,
 size_bytes INTEGER NOT NULL,
 thumbnail_bytes INTEGER,
 share_url TEXT,
 expires_at REAL,
 last_error TEXT
);
