-- Preserve all files already present at upgrade. Only confirmations made after
-- this migration schedule automatic working-file cleanup.
UPDATE session_finals SET cleanup_status='retained_legacy',cleanup_error=NULL
 WHERE cleanup_status IN ('pending','blocked');
CREATE TABLE IF NOT EXISTS booth_stations (
 token_hash TEXT PRIMARY KEY,auth_tag TEXT NOT NULL,expires_at REAL NOT NULL,created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS booth_sessions (
 session_id TEXT PRIMARY KEY REFERENCES sessions(id),station_hash TEXT NOT NULL REFERENCES booth_stations(token_hash)
);
PRAGMA user_version=7;
