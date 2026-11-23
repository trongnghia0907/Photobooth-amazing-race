import { get } from '@vercel/blob';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { blobKey, catalog, matches, personalToken, uuid } from '../lib/catalog.mjs';

const views = new Set(['gallery','event','preview','event-media','detail','image','download',
  'personal','personal-image','personal-download']);
const tokenPattern = /^([a-f0-9-]{36})\.[a-f0-9]{64}$/;
const photoContent = (url, personal) => `<h2 class="photo-heading">Ảnh của bạn</h2>
<img id="guestPhoto" src="${url}/image" alt="Ảnh của bạn">
<a id="guestDownload" href="${url}/download" download>${personal ? 'Download' : 'Tải ảnh về máy'}</a>`;

function page(res, status, content, personal) {
  res.setHeader('Content-Type','text/html; charset=utf-8');
  res.status(status).end(`<!doctype html><html lang="vi"${personal ? ' class="qr-photo-page"' : ''}><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Ảnh của bạn • AMAZING RACE 2026</title><link rel="stylesheet" href="/p/assets/photo.css">
</head><body><main><header class="guest-brand"><h1>AMAZING RACE 2026</h1></header>
<section>${content}</section></main></body></html>`);
}

export default async function publicPhotos(req, res) {
  return handlePublic(req,res);
}

export async function handlePublic(req, res, {open = catalog, read = get} = {}) {
  const {view,id,token,page:number} = req.query ?? {};
  const personal = typeof view === 'string' && view.startsWith('personal');
  const photoPage = view === 'personal' || view === 'detail';
  res.setHeader('Cache-Control','no-store');
  if (req.method !== 'GET' && req.method !== 'HEAD') return res.status(405).end();
  if (!views.has(view)) return res.status(404).end();
  const unavailable = () => photoPage
    ? page(res,404,'<h2>Không thể xem ảnh</h2><p role="alert">Liên kết đã hết hạn hoặc ảnh hiện không khả dụng.</p>',personal)
    : res.status(404).end();
  try {
    const db = open();
    if (view === 'gallery') {
      const total = await db.count();
      const pages = Math.max(1,Math.ceil(total/10));
      const current = Math.min(pages,Math.max(1,Number.parseInt(number,10)||1));
      const items = (await db.list(10,(current-1)*10)).map(photo => ({id:photo.id,width:photo.width,height:photo.height,
        preview_url:`/gallery/preview/${photo.id}`,photo_url:`/gallery/photo/${photo.id}`}));
      return res.status(200).json({items,total,pages,page:current,page_size:10});
    }
    if (view === 'event') {
      const items = (await db.list(100,0)).map(photo => ({id:photo.id,width:photo.width,height:photo.height,
        image_url:`/event-display/media/${photo.id}`,approved_at:new Date(photo.approved_at).getTime()/1000}));
      return res.status(200).json({items});
    }
    let photoId = id;
    if (personal) {
      photoId = typeof token === 'string' ? tokenPattern.exec(token)?.[1] : null;
      if (!photoId || !uuid.test(photoId) || !matches(token,personalToken(photoId))) return unavailable();
    }
    if (typeof photoId !== 'string' || !uuid.test(photoId)) return unavailable();
    const photo = await db.find(photoId);
    if (!photo?.approved || (personal && !(new Date(photo.expires_at).getTime() > Date.now()))) return unavailable();
    if (photoPage) return page(res,200,photoContent(personal ? `/p/${token}` : `/gallery/photo/${photoId}`,personal),personal);

    const thumbnail = view === 'preview';
    const options = {access:'private'};
    if (thumbnail || view === 'event-media') {
      res.setHeader('Cache-Control','private, no-cache');
      if (req.headers['if-none-match']) options.ifNoneMatch = req.headers['if-none-match'];
    }
    const result = await read(blobKey(photoId,thumbnail?photo.thumb_sha:photo.sha,thumbnail),options);
    if (!result) return unavailable();
    res.setHeader('ETag',result.blob.etag);
    if (result.statusCode === 304) return res.status(304).end();
    res.setHeader('Content-Type',thumbnail?'image/jpeg':'image/png');
    if (result.blob.size != null) res.setHeader('Content-Length',result.blob.size);
    if (view.endsWith('download')) res.setHeader('Content-Disposition',`attachment; filename="amazing-race-2026-${photoId}.png"`);
    if (req.method === 'HEAD') {
      await result.stream.cancel();
      return res.status(200).end();
    }
    return await pipeline(Readable.fromWeb(result.stream),res);
  } catch {
    if (res.headersSent || res.destroyed) return res.destroy();
    res.removeHeader('Content-Length');
    res.removeHeader('Content-Disposition');
    res.setHeader('Cache-Control','no-store');
    res.setHeader('Retry-After','5');
    if (photoPage) return page(res,503,'<h2>Ảnh đang được chuẩn bị</h2><p role="status">Vui lòng tải lại trang sau ít phút.</p>',personal);
    return res.status(503).end();
  }
}
