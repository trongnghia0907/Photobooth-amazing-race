CREATE TABLE IF NOT EXISTS session_finals (
 session_id TEXT PRIMARY KEY REFERENCES sessions(id),
 composite_id TEXT NOT NULL UNIQUE REFERENCES composites(id),
 confirmed_at TEXT NOT NULL,
 cleanup_status TEXT NOT NULL DEFAULT 'pending' CHECK(cleanup_status IN ('pending','complete','blocked','retained_legacy')),
 cleanup_error TEXT
);
CREATE TABLE IF NOT EXISTS temporary_file_cleanup (
 session_id TEXT NOT NULL REFERENCES session_finals(session_id),
 path TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','deleted')),
 PRIMARY KEY(session_id,path)
);
-- Preserve historical links. Ambiguous pre-upgrade edited/published sessions
-- are sealed to their last published final, but their working files are retained.
INSERT OR IGNORE INTO session_finals(session_id,composite_id,confirmed_at,cleanup_status)
 SELECT s.id,CASE WHEN s.status='completed' THEN s.composite_id ELSE
 (SELECT composite_id FROM shares WHERE session_id=s.id ORDER BY created_at DESC LIMIT 1) END,
 s.updated_at,CASE WHEN s.status='completed' THEN 'pending' ELSE 'retained_legacy' END
 FROM sessions s WHERE (s.status='completed' AND s.composite_id IS NOT NULL)
 OR EXISTS(SELECT 1 FROM shares WHERE session_id=s.id);
UPDATE sessions SET composite_id=(SELECT composite_id FROM session_finals WHERE session_id=sessions.id),status='completed'
 WHERE id IN (SELECT session_id FROM session_finals);
CREATE TRIGGER IF NOT EXISTS one_new_share_per_session BEFORE INSERT ON shares
 WHEN EXISTS(SELECT 1 FROM shares WHERE session_id=NEW.session_id)
 BEGIN SELECT RAISE(ABORT,'Session already has a share'); END;
PRAGMA user_version=6;
