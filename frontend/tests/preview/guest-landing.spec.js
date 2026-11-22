import {test,expect,request} from '@playwright/test';
import {randomBytes,randomUUID,createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';

let cookies,csrf;
test.beforeAll(async()=>{
  const api=await request.newContext({baseURL:'http://127.0.0.1:5188'});
  const paired=await api.post('/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:'preview-only-disposable-pairing-key'}});
  expect(paired.ok()).toBe(true);csrf=(await paired.json()).csrf_token;
  cookies=(await api.storageState()).cookies;await api.dispose();
});
test.beforeEach(async({context})=>context.addCookies(cookies));

async function confirmedPhoto(page,count){
  // Only disposable manual-upload fixtures. No camera or real photo is used.
  const fixture=await page.evaluate(count=>{
    const canvas=document.createElement('canvas');canvas.width=count===4?1800:1200;canvas.height=count===4?1200:1800;
    const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height;
    ctx.fillStyle='#1e40af';ctx.fillRect(0,0,w,h);const margin=50,cellW=(w-3*margin)/2,cellH=(h-160-(count/2+1)*margin)/(count/2);
    for(let i=0;i<count;i++){
      const x=margin+(i%2)*(cellW+margin),y=90+(i>>1)*(cellH+margin);
      ctx.fillStyle=['#6fbbc7','#d99c7e','#7ba89c','#8ba977','#9c9ebf','#c3af83'][i];ctx.fillRect(x,y,cellW,cellH);
      ctx.fillStyle='#16365b';ctx.font='bold 42px sans-serif';ctx.fillText('Photo '+(i+1),x+30,y+70);
    }
    ctx.fillStyle='#fff';ctx.font='bold 34px sans-serif';ctx.textAlign='center';ctx.fillText('AMAZING RACE 2026',w/2,55);
    const composite=canvas.toDataURL('image/png').split(',')[1];
    canvas.width=120;canvas.height=80;ctx.fillStyle='#6fbbc7';ctx.fillRect(0,0,120,80);
    return {composite,photo:canvas.toDataURL('image/png').split(',')[1]};
  },count);
  const owner=randomBytes(32).toString('hex');
  const headers=()=>({Authorization:'Bearer '+owner,'Idempotency-Key':randomUUID(),'X-Booth-CSRF':csrf});
  let response=await page.request.post('/api/sessions',{headers:headers(),data:{layout:count===4?'landscape_4':'grid2x3',slot_count:count}});
  expect(response.ok()).toBe(true);const sid=(await response.json()).session_id;let state;
  for(let slot=0;slot<count;slot++){
    response=await page.request.post(`/api/sessions/${sid}/photos`,{headers:headers(),multipart:{slot_index:String(slot),source:'manual_upload',
      file:{name:'working.png',mimeType:'image/png',buffer:Buffer.from(fixture.photo,'base64')}}});
    expect(response.ok()).toBe(true);state=await response.json();
  }
  response=await page.request.put(`/api/sessions/${sid}/composite`,{headers:headers(),multipart:{shots_revision:String(state.shots_revision),
    editor_json:JSON.stringify({event_display_consent:false}),file:{name:'final.png',mimeType:'image/png',buffer:Buffer.from(fixture.composite,'base64')}}});
  expect(response.ok()).toBe(true);const composite=(await response.json()).composite;
  const compositeId=composite.id;
  response=await page.request.post(`/api/sessions/${sid}/complete`,{headers:headers(),data:{composite_id:compositeId}});expect(response.ok()).toBe(true);
  response=await page.request.post(`/api/sessions/${sid}/finalize`,{headers:headers(),data:{composite_id:compositeId}});expect(response.ok()).toBe(true);
  const {share}=await response.json();
  return {path:new URL(share.share_url).pathname,original:composite};
}

const viewports=[{width:360,height:800},{width:390,height:844},{width:430,height:932},{width:768,height:1024}];
for(const count of [4,6])test(`${count}-photo public landing: mobile layout, exact artwork, download and alternate origin`,async({page,context})=>{
  const {path,original}=await confirmedPhoto(page,count);
  const expectedImage=await page.request.get(path+'/image');expect(expectedImage.ok()).toBe(true);
  expect(createHash('sha256').update(await expectedImage.body()).digest('hex')).toBe(original.sha256);
  const art=await page.request.get('/p/assets/theme.png');expect(art.ok()).toBe(true);
  expect(createHash('sha256').update(await art.body()).digest('hex')).toBe(createHash('sha256').update(readFileSync('public/assets/official-theme.png')).digest('hex'));
  for(const size of [...viewports,{width:1440,height:900}]){
    await page.setViewportSize(size);const response=await page.goto(path);expect(response.status()).toBe(200);
    const photo=page.locator('#guestPhoto'),download=page.locator('#guestDownload');await expect(photo).toBeVisible();await expect(download).toBeVisible();
    await expect(page.locator('img')).toHaveCount(1);
    const box=await photo.boundingBox(),button=await download.boundingBox();
    expect(await photo.evaluate(img=>[img.naturalWidth,img.naturalHeight])).toEqual([original.width,original.height]);
    const ratio=await photo.evaluate(img=>img.naturalWidth/img.naturalHeight);
    expect(Math.abs(box.width/box.height-ratio)).toBeLessThan(.02);
    expect(await photo.evaluate(img=>getComputedStyle(img).objectFit)).toBe('contain');
    expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(size.width);
    expect(button.y).toBeGreaterThanOrEqual(box.y+box.height);expect(button.height).toBeGreaterThanOrEqual(48);
    expect(button.y+button.height).toBeLessThanOrEqual(size.height);
    const background=await page.evaluate(()=>{
      const css=getComputedStyle(document.body,'::before');return {position:css.position,size:css.backgroundSize,image:css.backgroundImage,
        centered:css.backgroundPosition==='50% 50%',width:parseFloat(css.width),height:parseFloat(css.height),minHeight:parseFloat(getComputedStyle(document.body).minHeight),overflow:document.documentElement.scrollWidth>innerWidth};
    });
    expect(background.position).toBe('fixed');expect(background.size).toContain('cover');expect(background.image).toContain('/p/assets/theme.png');
    expect(background.centered).toBe(true);
    expect(background.width).toBe(size.width);expect(background.height).toBe(size.height);expect(background.minHeight).toBeGreaterThanOrEqual(size.height);expect(background.overflow).toBe(false);
    await expect(page.locator('meta[name=viewport]')).toHaveAttribute('content',/viewport-fit=cover/);
    await expect(page.locator('h1')).toBeVisible();
    await expect(download).toHaveText('Tải ảnh về máy');
    await page.screenshot({path:`test-results/preview/guest-photo-${count}-${size.width}x${size.height}.png`,fullPage:true});
  }
  // Simulate a smaller dynamic viewport and iOS inset padding on the same page.
  await page.setViewportSize({width:360,height:740});
  await page.evaluate(()=>{
    document.body.style.setProperty('--safe-top','44px');
    document.body.style.setProperty('--safe-bottom','34px');
    document.body.style.setProperty('--safe-left','12px');
    document.body.style.setProperty('--safe-right','12px');
  });
  const insetPhoto=await page.locator('#guestPhoto').boundingBox();
  const insetButton=await page.locator('#guestDownload').boundingBox();
  expect(insetPhoto.x).toBeGreaterThanOrEqual(12);
  expect(insetPhoto.x+insetPhoto.width).toBeLessThanOrEqual(348);
  expect(insetPhoto.y).toBeGreaterThanOrEqual(44);
  expect(insetButton.y+insetButton.height).toBeLessThanOrEqual(706);
  const pending=page.waitForEvent('download');await page.locator('#guestDownload').click();
  const downloaded=await pending;expect(createHash('sha256').update(readFileSync(await downloaded.path())).digest('hex')).toBe(original.sha256);
  expect(downloaded.suggestedFilename()).toMatch(/^amazing-race-2026-photo-.*\.png$/);
  // Synthetic future HTTPS domain; every request is proxied to the disposable
  // local test server, never to the Internet or an operator's tunnel.
  const remote=await context.newPage();const origin='https://public-photo.example.test';
  await remote.route(origin+'/**',async route=>{
    const url=new URL(route.request().url());const response=await page.request.get(url.pathname+url.search);await route.fulfill({response});
  });
  await remote.setViewportSize(viewports[1]);await remote.goto(origin+path);
  await expect(remote.locator('#guestPhoto')).toBeVisible();await expect(remote.locator('#guestDownload')).toHaveAttribute('href',path+'/download');
  await remote.close();
});

test('loading, image failure, recovery and unavailable page keep usable status messages',async({page})=>{
  const {path}=await confirmedPhoto(page,6);await page.setViewportSize(viewports[0]);
  let release;const held=new Promise(resolve=>release=resolve);let fail=true;
  await page.route('**/p/*/image*',async route=>{
    await held;if(fail)return route.abort('failed');return route.fallback();
  });
  await page.goto(path,{waitUntil:'domcontentloaded'});await expect(page.locator('#loading')).toBeVisible();await expect(page.locator('#guestDownload')).toBeHidden();
  release();await expect(page.locator('#error')).toBeVisible();await expect(page.locator('#guestDownload')).toBeHidden();
  fail=false;await expect(page.locator('#guestPhoto')).toBeVisible({timeout:12000});
  await expect(page.locator('#guestDownload')).toBeVisible();await expect(page.locator('#error')).toBeHidden();
  for(const size of viewports){
    await page.setViewportSize(size);const response=await page.goto('/p/not-valid');expect(response.status()).toBe(404);
    await expect(page.locator('[role=alert]')).toBeVisible();await expect(page.locator('h1')).toBeVisible();
    expect(await page.locator('#guestDownload').count()).toBe(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
});
