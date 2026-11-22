import { get } from '@vercel/blob';
import { createHash } from 'node:crypto';
import { blobKey, catalog, matches, personalToken, uuid } from '../lib/catalog.mjs';

const sha256 = /^[a-f0-9]{64}$/;
const positiveInt = (value, max) => Number.isSafeInteger(value) && value > 0 && value <= max;

async function verifyBlob(key, sha, size, mime) {
  const result = await get(key, {access:'private', abortSignal:AbortSignal.timeout(12000)});
  if (!result?.stream) return false;
  if (result.blob.contentType !== mime || result.blob.size !== size) {
    await result.stream.cancel();
    return false;
  }
  const hash = createHash('sha256');
  let received = 0;
  for await (const chunk of result.stream) {
    received += chunk.length;
    if (received > size) return false;
    hash.update(chunk);
  }
  return received === size && hash.digest('hex') === sha;
}

export default async function publication(req, res) {
  return handlePublication(req, res);
}

export async function handlePublication(req, res, {open = catalog, verify = verifyBlob} = {}) {
  res.setHeader('Cache-Control','no-store');
  if (req.method !== 'POST') return res.status(405).json({error:'Method not allowed'});
  const secret = process.env.PHOTO_CLOUD_PUBLISH_SECRET;
  if (!secret || secret.length < 32 || !matches(req.headers.authorization, `Bearer ${secret}`)) {
    return res.status(401).json({error:'Unauthorized'});
  }
  let item = req.body;
  if (typeof item === 'string') {
    try { item = JSON.parse(item); } catch { /* rejected below */ }
  }
  if (!item || typeof item.id !== 'string' || !uuid.test(item.id)
      || !positiveInt(item.version, 2147483647) || typeof item.approved !== 'boolean'
      || (item.approved && (typeof item.sha !== 'string' || typeof item.thumb_sha !== 'string'
        || !sha256.test(item.sha) || !sha256.test(item.thumb_sha) || !positiveInt(item.size, 100 * 1024 * 1024)
        || !positiveInt(item.thumb_size, 1024 * 1024) || !positiveInt(item.width, 12000)
        || !positiveInt(item.height, 12000)))) return res.status(422).json({error:'Invalid publication'});

  try {
    const db = open();
    const existing = await db.find(item.id);
    if (existing?.version > item.version) return res.status(409).json({error:'Stale version'});
    const token = item.approved ? personalToken(item.id) : null;
    if ((!existing || existing.version < item.version) && item.approved) {
      if ((existing?.sha && existing.sha !== item.sha) || !(await verify(blobKey(item.id,item.sha),item.sha,item.size,'image/png'))
          || !(await verify(blobKey(item.id,item.thumb_sha,true),item.thumb_sha,item.thumb_size,'image/jpeg'))) {
        return res.status(409).json({error:'Blob verification failed'});
      }
    }
    const row = await db.set(item.approved ? item : {id:item.id, version:item.version, approved:false});
    if (row.version !== item.version || row.approved !== item.approved || (item.approved && row.sha !== item.sha)) {
      return res.status(409).json({error:'Publication version conflict'});
    }
    return res.status(200).json({version:row.version, share_path:token && `/p/${token}`,
      expires_at:token && new Date(row.expires_at).getTime()/1000});
  } catch {
    return res.status(503).json({error:'Publication temporarily unavailable'});
  }
}
