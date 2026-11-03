import test from 'node:test';
import assert from 'node:assert/strict';
import {refreshRecentGallery} from '../src/features/home/kiosk.js';

test('recent gallery diagnoses a stale backend and recovers without losing approved photos during connection loss',async()=>{
  const originalFetch=globalThis.fetch;
  const previous=[{id:'approved-a',image_url:'/api/booth/recent-photos/approved-a'}];
  const app={recentGalleryItems:previous,recentGalleryLoaded:true,recentGalleryBusy:false,recentGalleryError:'',renderRecentPhotos(){}};
  try{
    globalThis.fetch=async()=>new Response('{}',{status:404});
    await refreshRecentGallery(app);
    assert.match(app.recentGalleryError,/backend is outdated.*404.*run_host\.py --build/);
    assert.equal(app.recentGalleryItems,previous);
    assert.equal(app.recentGalleryBusy,false);

    globalThis.fetch=async()=>{throw new TypeError('Failed to fetch');};
    await refreshRecentGallery(app);
    assert.match(app.recentGalleryError,/Could not connect to the host laptop/);
    assert.equal(app.recentGalleryItems,previous);

    globalThis.fetch=async()=>new Response('<html>Wrong frontend server</html>',{status:200});
    await refreshRecentGallery(app);
    assert.match(app.recentGalleryError,/photo feed returned an invalid response/);
    assert.equal(app.recentGalleryItems,previous);

    globalThis.fetch=async()=>new Response('{}',{status:401});
    await refreshRecentGallery(app);
    assert.match(app.recentGalleryError,/Pair this kiosk with the host/);

    const newest=[{id:'approved-b',image_url:'/api/booth/recent-photos/approved-b'},...previous];
    globalThis.fetch=async()=>Response.json({items:newest});
    await refreshRecentGallery(app);
    assert.deepEqual(app.recentGalleryItems,newest);
    assert.equal(app.recentGalleryError,'');
    assert.equal(app.recentGalleryLoaded,true);
  }finally{globalThis.fetch=originalFetch;}
});
