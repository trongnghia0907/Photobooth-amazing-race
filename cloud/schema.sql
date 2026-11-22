CREATE TABLE IF NOT EXISTS photos (
  id uuid PRIMARY KEY,
  version integer NOT NULL,
  approved boolean NOT NULL,
  sha text,
  thumb_sha text,
  width integer,
  height integer,
  approved_at timestamptz,
  expires_at timestamptz
);

CREATE INDEX IF NOT EXISTS photos_public_order ON photos (approved_at DESC, id DESC) WHERE approved;
