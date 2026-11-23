ALTER TABLE cloud_publications ADD COLUMN remote_started INTEGER;
CREATE TABLE photo_deletions (
    composite_id TEXT PRIMARY KEY REFERENCES composites(id),
    cloud_pending INTEGER NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    next_attempt REAL NOT NULL DEFAULT 0,
    last_error TEXT
);
PRAGMA user_version=11;
