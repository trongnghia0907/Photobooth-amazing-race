import { neon } from '@neondatabase/serverless';
import { createHmac, timingSafeEqual } from 'node:crypto';

export const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
// Reserve the highest integer version for permanent deletion. No normal
// publication can replace this ID or recover its cleared metadata.
export const deletedVersion = 2147483647;

export const blobKey = (id, sha, thumbnail = false) => `photos/${id}/${sha}.${thumbnail ? 'jpg' : 'png'}`;

export function matches(actual, expected) {
  const a = Buffer.from(actual || '');
  const b = Buffer.from(expected || '');
  return a.length === b.length && timingSafeEqual(a, b);
}

export function personalToken(id, secret = process.env.PHOTO_CLOUD_QR_SECRET) {
  if (typeof secret !== 'string' || secret.length < 32) throw new Error('QR secret is missing');
  return `${id}.${createHmac('sha256', secret).update(id).digest('hex')}`;
}

export function catalog(sql = neon(process.env.DATABASE_URL)) {
  return {
    async find(id) {
      return (await sql`SELECT * FROM photos WHERE id=${id}`)[0];
    },
    async markDeleted(id) {
      await sql`INSERT INTO photos (id,version,approved) VALUES (${id},${deletedVersion},false)
        ON CONFLICT (id) DO UPDATE SET version=excluded.version, approved=false,
          sha=NULL, thumb_sha=NULL, width=NULL, height=NULL, approved_at=NULL, expires_at=NULL`;
    },
    async set(item) {
      const {id, version, approved, sha = null, thumb_sha = null, width = null, height = null} = item;
      // A tombstone is valid even if it arrives before any publication. Keep
      // the first QR expiry through retries and hide/reapproval.
      const [row] = await sql`INSERT INTO photos (id,version,approved,sha,thumb_sha,width,height,approved_at,expires_at)
        VALUES (${id},${version},${approved},${sha},${thumb_sha},${width},${height},
          CASE WHEN ${approved} THEN now() END, CASE WHEN ${approved} THEN now()+interval '24 hours' END)
        ON CONFLICT (id) DO UPDATE SET version=excluded.version, approved=excluded.approved,
          sha=coalesce(excluded.sha,photos.sha), thumb_sha=coalesce(excluded.thumb_sha,photos.thumb_sha),
          width=coalesce(excluded.width,photos.width), height=coalesce(excluded.height,photos.height),
          approved_at=excluded.approved_at, expires_at=coalesce(photos.expires_at,excluded.expires_at)
        WHERE photos.version<excluded.version RETURNING *`;
      return row || (await this.find(id));
    },
    async list(limit, offset) {
      return sql`SELECT id,width,height,approved_at FROM photos WHERE approved
        ORDER BY approved_at DESC,id DESC LIMIT ${limit} OFFSET ${offset}`;
    },
    async count() {
      const [row] = await sql`SELECT count(*)::int AS total FROM photos WHERE approved`;
      return row.total;
    },
  };
}
