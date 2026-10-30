-- Explicit opt-in only. Existing and future photos are private by default.
CREATE TABLE IF NOT EXISTS event_display_config (
 id INTEGER PRIMARY KEY CHECK(id=1), access_hash TEXT
);
INSERT OR IGNORE INTO event_display_config(id) VALUES(1);
CREATE TABLE IF NOT EXISTS event_display_sessions (
 token_hash TEXT PRIMARY KEY, expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS event_display_photos (
 session_id TEXT PRIMARY KEY REFERENCES session_finals(session_id),
 composite_id TEXT NOT NULL UNIQUE REFERENCES composites(id),
 display_id TEXT NOT NULL UNIQUE,
 approved INTEGER NOT NULL CHECK(approved IN (0,1)),
 approval_basis TEXT NOT NULL CHECK(approval_basis IN ('guest_consent','event_authorization')),
 approved_by TEXT NOT NULL, approved_at REAL NOT NULL, hidden_at REAL
);
CREATE INDEX IF NOT EXISTS event_display_order ON event_display_photos(approved,approved_at DESC);
PRAGMA user_version=8;
