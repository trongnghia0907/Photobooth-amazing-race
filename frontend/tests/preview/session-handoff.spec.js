import {test,expect,request} from '@playwright/test';
let cookies;
test.beforeAll(async()=>{
  const api=await request.newContext({baseURL:'http://127.0.0.1:5188'});
  expect((await api.post('/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:'preview-only-disposable-pairing-key'}})).ok()).toBe(true);
  cookies=(await api.storageState()).cookies;await api.dispose();
});
test.beforeEach(async({context})=>context.addCookies(cookies));
test.afterEach(async({page})=>page.evaluate(async()=>{app.releaseHostCamera();await app.hostReleaseRequest;}).catch(()=>{}));

test('failed camera request can move to New Session without carrying its request key or photo',async({page})=>{
  page.on('dialog',dialog=>dialog.accept());
  await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  const old=await page.evaluate(()=>app.sessionContext.id);
  await page.route('**/camera/captures',route=>route.fulfill({status:503,json:{error:{code:'timeout',stage:'transfer',uncertain:false,message:'TEST lost old transfer'}}}));
  await page.evaluate(async()=>{try{await app.capturePhoto(0);}catch{}});
  await page.waitForFunction(()=>!!app.hostCaptureOperation);
  await page.locator('#newSessionButton').click();
  await page.waitForFunction(id=>app.sessionContext?.id&&app.sessionContext.id!==id&&app.hostPreviewHealthy,old);
  expect(await page.evaluate(()=>app.hostCaptureOperation)).toBeNull();
  expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(0);
  await page.unroute('**/camera/captures');
  await page.evaluate(()=>app.capturePhoto(0));
  expect(await page.evaluate(()=>app.serverSession.photos.length)).toBe(1);
  expect(await page.evaluate(()=>app.serverSession.finalized)).toBe(false);
});

test('24MP thumbnail benchmark: original size untouched, bounded thumbnail and cached repeated rendering',async({page})=>{
  await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  const result=await page.evaluate(async()=>{
    const {photoThumbnail}=await import('/src/utils/photo-thumbnail.js');
    const source=document.createElement('canvas');source.width=6000;source.height=4000;
    const tile=document.createElement('canvas');tile.width=tile.height=256;
    const ctx=tile.getContext('2d'),pixels=ctx.createImageData(256,256);let seed=17;
    for(let i=0;i<pixels.data.length;i+=4){seed=(seed*1664525+1013904223)>>>0;pixels.data[i]=seed&255;pixels.data[i+1]=(seed>>>8)&255;pixels.data[i+2]=(seed>>>16)&255;pixels.data[i+3]=255;}
    ctx.putImageData(pixels,0,0);const full=source.getContext('2d');full.fillStyle=full.createPattern(tile,'repeat');full.fillRect(0,0,6000,4000);
    const before=[],after=[];let originalLength=0,url;
    for(let i=0;i<5;i++){const at=performance.now();originalLength=source.toDataURL('image/jpeg',.85).length;before.push(performance.now()-at);}
    const first=performance.now();url=photoThumbnail(source);const firstThumbnailMs=performance.now()-first;
    for(let i=0;i<5;i++){const at=performance.now();for(let j=0;j<6;j++)photoThumbnail(source);after.push(performance.now()-at);}
    const image=new Image();image.src=url;await image.decode();
    return {source:[source.width,source.height],thumbnail:[image.width,image.height],originalDataUrlBytes:originalLength,thumbnailDataUrlBytes:url.length,
      beforeEncodeMs:before.sort((a,b)=>a-b)[2],firstThumbnailMs,cachedSixTilesMs:after.sort((a,b)=>a-b)[2]};
  });
  expect(result.source).toEqual([6000,4000]);expect(result.thumbnail).toEqual([640,427]);
  expect(result.thumbnailDataUrlBytes).toBeLessThan(result.originalDataUrlBytes);
  console.log('SYNTHETIC 24MP UI thumbnail benchmark (not camera/LAN):',JSON.stringify(result));
});

test('sidebar adds only the new thumbnail and keeps existing photo nodes on polling updates',async({page})=>{
  let downloads=0;
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==','base64');
  await page.route('**/api/booth/recent-photos/*',route=>{downloads++;return route.fulfill({contentType:'image/png',body:png});});
  await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  const set=ids=>page.evaluate(ids=>{app.recentGalleryItems=ids.map(id=>({id,image_url:'/api/booth/recent-photos/'+id+'?thumbnail=true'}));app.renderRecentPhotos();},ids);
  await set(['a','b']);await expect.poll(()=>downloads).toBe(2);
  const a=await page.locator('#recentPhotoList img[data-display-id="a"]').elementHandle();
  await set(['c','a','b']);await expect.poll(()=>downloads).toBe(3);
  expect(await a.evaluate(node=>node===document.querySelector('#recentPhotoList img[data-display-id="a"]'))).toBe(true);
  await set(['a','b']);await expect(page.locator('#recentPhotoList img')).toHaveCount(2);
  expect(downloads).toBe(3);
});
