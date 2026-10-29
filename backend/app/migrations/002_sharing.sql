CREATE TABLE shares (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    composite_id TEXT NOT NULL UNIQUE REFERENCES composites(id),
    token_hash TEXT NOT NULL UNIQUE,
    nonce TEXT NOT NULL,
    public_base_url TEXT NOT NULL,
    qr_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    expires_at TEXT
);
CREATE INDEX shares_session ON shares(session_id);
PRAGMA user_version = 2;
