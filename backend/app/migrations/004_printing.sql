CREATE TABLE IF NOT EXISTS print_ready (
 final_id TEXT PRIMARY KEY REFERENCES shares(id), path TEXT NOT NULL UNIQUE,
 sha256 TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
 source_height INTEGER NOT NULL, qr_x INTEGER NOT NULL, qr_y INTEGER NOT NULL,
 qr_size INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS print_jobs (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
 session_id TEXT NOT NULL REFERENCES sessions(id), final_id TEXT NOT NULL REFERENCES print_ready(final_id),
 print_ready_file TEXT NOT NULL, sha256 TEXT NOT NULL, copies INTEGER NOT NULL CHECK(copies>0),
 status TEXT NOT NULL CHECK(status IN ('queued','processing','submitted','failed','cancelled')),
 mode TEXT NOT NULL, printer_id TEXT NOT NULL,
 scope TEXT NOT NULL, request_key TEXT NOT NULL, payload_hash TEXT NOT NULL,
 retry_of TEXT REFERENCES print_jobs(id), receipt_json TEXT,
 error_message TEXT, uncertain INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(scope,request_key)
);
CREATE INDEX IF NOT EXISTS print_queue ON print_jobs(status,seq);
CREATE TABLE IF NOT EXISTS host_settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS admin_credentials (id INTEGER PRIMARY KEY CHECK(id=1),username TEXT NOT NULL,password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS admin_sessions (token_hash TEXT PRIMARY KEY,auth_tag TEXT NOT NULL,expires_at REAL NOT NULL);
PRAGMA user_version=4;
