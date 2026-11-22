// Run by the Windows Host's background worker, never deployed as a route.
import { BlobNotFoundError, head, put } from '@vercel/blob';
import { createHash } from 'node:crypto';

const [key, mime] = process.argv.slice(2);
const match = /^photos\/[a-f0-9-]{36}\/([a-f0-9]{64})\.(png|jpg)$/.exec(key);
if (!match || mime !== (match[2] === 'png' ? 'image/png' : 'image/jpeg')) process.exit(1);
const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const bytes = Buffer.concat(chunks);
if (createHash('sha256').update(bytes).digest('hex') !== match[1]) process.exit(1);

try {
  const existing = await head(key);
  if (existing.size !== bytes.length || existing.contentType !== mime) process.exit(1);
} catch (error) {
  if (!(error instanceof BlobNotFoundError)) throw error;
  await put(key, bytes, {access:'private', contentType:mime, addRandomSuffix:false,
    allowOverwrite:false, multipart:bytes.length > 5_000_000});
}
