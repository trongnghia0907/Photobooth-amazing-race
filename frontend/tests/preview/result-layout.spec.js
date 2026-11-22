import {test,expect,request} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

let cookies;
test.beforeAll(async()=>{
  const api=await request.newContext({baseURL:'http://127.0.0.1:5188'});
  const response=await api.post('/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:'preview-only-disposable-pairing-key'}});
  expect(response.ok()).toBe(true);cookies=(await api.storageState()).cookies;await api.dispose();
});
test.beforeEach(async({context,page})=>{
  await context.addCookies(cookies);
  // Verify layout using the isolated Mock backend. Only external HTTPS
  // availability is simulated; persistence, QR/footer and printing are real APIs.
  await page.route('**/api/sessions/*/public-status',async route=>{
    const sid=new URL(route.request().url()).pathname.split('/')[3];
    const response=await page.request.get('/api/sessions/'+sid,{headers:{Authorization:route.request().headers().authorization}});
    const state=await response.json();
    await route.fulfill({json:{...state.share,public_ready:true,expires_at:new Date(Date.now()+86400000).toISOString()}});
  });
});
test.afterEach(async({page})=>{
  await page.evaluate(async()=>{app.releaseHostCamera();await app.hostReleaseRequest;}).catch(()=>{});
});

const viewports=[{width:1366,height:768},{width:1920,height:1080},{width:1024,height:768},
  {width:1180,height:820},{width:768,height:1024},{width:390,height:844}];

for(const count of [4,6])test(`${count}-photo final result: responsive preview, QR, download and print`,async({page})=>{
  await page.setViewportSize(viewports[0]);await page.goto('/');
  await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  if(count===4){await page.locator('#frameCardLandscape4').click();await page.waitForFunction(()=>!app.persistenceBusy);}
  await page.evaluate(async count=>{
    app.guestWorkflowActive=true;app.fullAutoMode=false;app.goToScreen('capture');
    for(let slot=0;slot<count;slot++)await app.captureHostPhoto(slot);
    await app.finishCaptureAndGoToResult();
  },count);
  const canvas=page.locator('#compositeCanvas');
  const confirm=page.locator('#confirmSessionBtn');
  for(const viewport of viewports.slice(0,2)){
    await page.setViewportSize(viewport);
    const preview=await canvas.boundingBox(), button=await confirm.boundingBox();
    expect(preview.height).toBeGreaterThan(viewport.height*.43);
    expect(preview.y+preview.height).toBeLessThanOrEqual(button.y);
    expect(button.y+button.height).toBeLessThanOrEqual(viewport.height);
    const ratio=await canvas.evaluate(c=>c.width/c.height);
    expect(Math.abs(preview.width/preview.height-ratio)).toBeLessThan(.02);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  const originalCanvas=await canvas.evaluate(c=>c.toDataURL());
  await page.locator('#confirmSessionBtn').click();
  await expect(page.locator('body')).toHaveAttribute('data-workflow','delivery');
  await expect(page.locator('#qrCodeContainer')).toHaveAttribute('data-phase','ready');
  const image=page.locator('#printReadyPreview');
  await expect(image).toBeVisible();await expect.poll(()=>image.evaluate(img=>img.naturalWidth)).toBeGreaterThan(0);
  const source=await image.getAttribute('src');
  const imageResponse=await page.request.get(source);expect(imageResponse.ok()).toBe(true);
  const expectedHash=await page.evaluate(()=>app.serverSession.composite.sha256);
  expect(createHash('sha256').update(await imageResponse.body()).digest('hex')).toBe(
    await page.evaluate(()=>app.activeShare.print_ready.sha256));
  for(const close of await page.locator('#toastContainer button').all())await close.click();
  for(const viewport of viewports){
    await page.setViewportSize(viewport);await page.evaluate(()=>document.querySelector('main').scrollTo(0,0));
    const photo=await image.boundingBox(),qr=await page.locator('#qrCodeContainer').boundingBox();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    expect(await image.evaluate(img=>getComputedStyle(img).objectFit)).toBe('contain');
    const ratio=await image.evaluate(img=>img.naturalWidth/img.naturalHeight);
    expect(Math.abs(photo.width/photo.height-ratio)).toBeLessThan(.02);
    if(viewport.width>=960){
      expect(photo.height).toBeGreaterThan(viewport.height*.60);
      expect(photo.y+photo.height).toBeLessThanOrEqual(viewport.height);
      expect(photo.height).toBeGreaterThan(qr.height*1.7);
      expect(photo.x+photo.width).toBeLessThanOrEqual(qr.x+1);
      for(const id of ['downloadPhotoBtn','printPhotoBtn','printCopies']){
        const box=await page.locator('#'+id).boundingBox();
        expect(box.height).toBeGreaterThanOrEqual(44);
        expect(box.y+box.height).toBeLessThanOrEqual(viewport.height);
      }
    }else{
      expect(qr.y).toBeGreaterThanOrEqual(photo.y+photo.height);
      await page.locator('#printPhotoBtn').scrollIntoViewIfNeeded();
      await expect(page.locator('#printPhotoBtn')).toBeInViewport();
    }
    for(const id of ['downloadPhotoBtn','printPhotoBtn','printCopies']){
      const box=await page.locator('#'+id).boundingBox();expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x+box.width).toBeLessThanOrEqual(viewport.width);
    }
    await page.evaluate(()=>{window.scrollTo(0,0);document.querySelector('main').scrollTo(0,0);});
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(resolve)));
    await page.screenshot({path:`test-results/preview/final-result-${count}-${viewport.width}x${viewport.height}.png`,fullPage:true});
  }
  expect(await image.getAttribute('src')).toBe(source);
  expect(await page.locator('#compositeCanvas').evaluate(canvas=>canvas.toDataURL())).toBe(originalCanvas);
  expect(await page.locator('#compositeCanvas').evaluate(canvas=>[canvas.width,canvas.height])).toEqual(count===4?[1800,1200]:[1200,1800]);
  await page.setViewportSize(viewports[0]);
  const pending=page.waitForEvent('download');await page.locator('#downloadPhotoBtn').click();
  const downloaded=await pending;
  expect(createHash('sha256').update(readFileSync(await downloaded.path())).digest('hex')).toBe(expectedHash);
  await page.locator('#printCopies').selectOption('2');await page.locator('#printPhotoBtn').click();
  await expect(page.locator('#printStatus')).toHaveText('Test print request received.');
  await expect(page.locator('#qrExpiryMessage')).toHaveText('Your QR code expires in 24 hours.');
  const savedPhoto=await page.evaluate(()=>app.activeShare.share_url);
  await page.locator('#newSessionButton').click();
  await expect(page.locator('body')).toHaveAttribute('data-workflow','setup');
  await expect(page.locator('#setupRecentSidebar')).toBeVisible();
  expect(await page.evaluate(()=>app.photos.every(photo=>photo===null))).toBe(true);
  // Resetting the UI must preserve the previous guest's completed download.
  const preserved=await page.request.get(new URL(savedPhoto).pathname+'/download');
  expect(preserved.ok()).toBe(true);
  expect(createHash('sha256').update(await preserved.body()).digest('hex')).toBe(expectedHash);
});
