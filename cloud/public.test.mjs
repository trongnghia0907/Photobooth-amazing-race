import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { Readable } from 'node:stream';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { handlePublic } from './api/public.mjs';
import { handlePublication } from './api/publication.mjs';
import { blobKey, personalToken } from './lib/catalog.mjs';

const routes = JSON.parse(await readFile(new URL('./vercel.json',import.meta.url))).rewrites;
const publishSecret = 'local-test-publish-secret'.repeat(3);
process.env.PHOTO_CLOUD_PUBLISH_SECRET = publishSecret;
process.env.PHOTO_CLOUD_QR_SECRET = 'local-test-qr-secret'.repeat(3);
const id = 'd96fda40-c7d1-4e31-861c-4e5bfba50a0c';
const checksum = data => createHash('sha256').update(data).digest('hex');
const original = await readFile(new URL('../theme/Theme-display.png',import.meta.url));
const thumbnail = Buffer.from('fixture thumbnail');
const item = {id,version:1,approved:true,sha:checksum(original),size:original.length,width:1920,height:1080,
  thumb_sha:checksum(thumbnail),thumb_size:thumbnail.length};

test('public route contracts share one approved asset and enforce expiry and hide', async t => {
  const data = new Map();
  const objects = new Map([[blobKey(id,item.sha),original],[blobKey(id,item.thumb_sha,true),thumbnail]]);
  const open = () => ({find:key=>data.get(key),count:()=>Array.from(data.values()).filter(row=>row.approved).length,
    list:(limit,offset)=>Array.from(data.values()).filter(row=>row.approved).slice(offset,offset+limit),
    set(value){
      const before = data.get(value.id);
      if (before?.version >= value.version) return before;
      const row = {...before,...value,approved_at:new Date(),expires_at:before?.expires_at || new Date(Date.now()+86400000)};
      data.set(row.id,row);
      return row;
    }});
  const checked = [];
  const verify = (key, sha, size) => {
    checked.push(key);
    const bytes = objects.get(key);
    return bytes?.length === size && checksum(bytes) === sha;
  };
  const read = (key, options) => {
    assert.equal(options.access,'private');
    const bytes = objects.get(key);
    if (!bytes) return null;
    const blob = {size:bytes.length,etag:'"fixture"'};
    return options.ifNoneMatch === blob.etag ? {statusCode:304,blob,stream:null}
      : {statusCode:200,blob,stream:Readable.toWeb(Readable.from([bytes]))};
  };
  const server = createServer(async (req,res) => {
    res.status = status => {res.statusCode=status;return res;};
    res.json = body => res.end(JSON.stringify(body));
    const url = new URL(req.url,'http://localhost');
    if (url.pathname === '/api/publication') {
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      req.body = Buffer.concat(chunks).toString('utf8');
      return handlePublication(req,res,{open,verify});
    }
    for (const {source,destination} of routes) {
      const match = new RegExp('^'+source.replace(/:(\w+)/g,'(?<$1>[^/]+)')+'$').exec(url.pathname);
      if (match && destination.startsWith('/api/public?')) {
        const query = new URL(destination.replace(/:(\w+)/g,(_,key)=>match.groups[key]),url);
        req.query = {...Object.fromEntries(url.searchParams),...Object.fromEntries(query.searchParams)};
        return handlePublic(req,res,{open,read});
      }
    }
    return res.status(404).end();
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  t.after(()=>new Promise(resolve=>server.close(resolve)));
  const root = `http://127.0.0.1:${server.address().port}`;
  const publish = (body, secret = publishSecret) => fetch(root+'/api/publication',{
    method:'POST',headers:{authorization:`Bearer ${secret}`},body:JSON.stringify(body)});
  const payload = async path => Buffer.from(await (await fetch(root+path)).arrayBuffer());

  assert.equal((await publish(item,'wrong')).status,401);
  assert.equal((await publish({...item,size:item.size-1})).status,409);
  checked.length = 0;
  const receipt = await (await publish(item)).json();
  assert.deepEqual(await (await publish(item)).json(),receipt);
  assert.equal(checked.length,2);
  assert.equal(receipt.share_path,`/p/${personalToken(id)}`);

  const gallery = await (await fetch(root+'/gallery/api/photos?page=99')).json();
  assert.equal(gallery.total,1);
  assert.equal(gallery.page,1);
  const galleryItem = gallery.items[0];
  assert.deepEqual(await payload(galleryItem.preview_url),thumbnail);
  assert.equal((await fetch(root+galleryItem.preview_url,{headers:{'If-None-Match':'"fixture"'}})).status,304);
  const event = await (await fetch(root+'/event-display/api/photos')).json();
  assert.equal(event.items[0].id,galleryItem.id);
  const html = await (await fetch(root+receipt.share_path)).text();
  assert.ok(html.includes(receipt.share_path+'/image') && html.includes(receipt.share_path+'/download'));
  assert.doesNotMatch(html,/qr\.png|print_ready/);
  for (const path of [galleryItem.photo_url+'/image',galleryItem.photo_url+'/download',event.items[0].image_url,
    receipt.share_path+'/image',receipt.share_path+'/download']) assert.deepEqual(await payload(path),original);

  data.get(id).expires_at = new Date(0);
  assert.equal((await fetch(root+receipt.share_path)).status,404);
  assert.deepEqual(await payload(galleryItem.photo_url+'/download'),original);
  assert.equal((await fetch(root+'/p/forged')).status,404);
  assert.equal((await publish({id,version:2,approved:false})).status,200);
  assert.equal((await publish(item)).status,409);
  assert.equal((await fetch(root+galleryItem.preview_url,{headers:{'If-None-Match':'"fixture"'}})).status,404);
  assert.equal((await fetch(root+event.items[0].image_url)).status,404);
  for (const path of ['/admin','/api/admin','/api/camera','/api/sessions','/api/print-config','/health']) {
    assert.equal((await fetch(root+path)).status,404);
  }
});
