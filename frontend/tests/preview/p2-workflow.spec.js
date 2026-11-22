import {test,expect} from '@playwright/test';
import {createHash} from 'node:crypto';

const host='http://127.0.0.1:8028';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');

for(const count of [4,6])test(`P2 local Host without cloud credentials: ${count} photos`,async({page})=>{
  const pair=await page.request.post(host+'/api/booth/pair',{
    headers:{'X-OSA-Pair':'1'}, data:{key:'preview-only-disposable-pairing-key'},
  });
  expect(pair.ok()).toBe(true);
  const health=await (await page.request.get(host+'/api/health')).json();
  expect(health.sharing.cloud_configured).toBe(false);
  // Only the external gateway handshake is simulated. Local QR, gallery,
  // event images, print derivative and the Mock queue use the real Host.
  await page.route('**/api/sessions/*/public-status',async route=>{
    const url=new URL(route.request().url());
    const session=await page.request.get(url.href.replace('/public-status',''),{
      headers:{Authorization:route.request().headers().authorization},
    });
    const state=await session.json();
    await route.fulfill({json:{...state.share,public_ready:true,expires_at:new Date(Date.now()+86400000).toISOString()}});
  });
  await page.goto(host+'/');
  await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  if(count===4){await page.locator('#frameCardLandscape4').click();await page.waitForFunction(()=>!app.persistenceBusy);}
  await page.evaluate(async slots=>{
    app.guestWorkflowActive=true;app.fullAutoMode=false;app.goToScreen('capture');
    for(let slot=0;slot<slots;slot++)await app.captureHostPhoto(slot);
    await app.finishCaptureAndGoToResult();
  },count);
  await page.locator('#confirmSessionBtn').click();
  await expect(page.locator('#qrCodeContainer')).toHaveAttribute('data-phase','ready');
  const {share,composite}=await page.evaluate(()=>({share:app.activeShare,composite:app.serverSession.composite}));
  expect([composite.width,composite.height]).toEqual(count===4?[1800,1200]:[1200,1800]);
  const qrPath=new URL(share.share_url).pathname;
  const download=await page.request.get(host+qrPath+'/download');
  expect(download.ok()).toBe(true);
  const original=await download.body();
  expect(sha(original)).toBe(composite.sha256);
  console.log(`P2 fixture ${count} slots: ${composite.width}x${composite.height}, ${original.length} bytes`);
  await expect(page.locator('#printReadyPreview')).toBeVisible();
  await page.locator('#printCopies').selectOption('2');await page.locator('#printPhotoBtn').click();
  await expect(page.locator('#printStatus')).toHaveText('Test print request received.');

  const gallery=await page.context().newPage();
  await gallery.goto(host+'/gallery');
  const recent=gallery.locator('#photoGrid .photo-card').first();
  await expect(recent).toBeVisible();
  const photoPath=await recent.getAttribute('href');
  expect(sha(await (await gallery.request.get(host+photoPath+'/download')).body())).toBe(composite.sha256);
  const display=await page.context().newPage();
  await display.goto(host+'/event-display');
  await expect(display.locator('#photoWall figure img').first()).toBeVisible();
  const guest=await page.context().newPage();
  await guest.setViewportSize({width:390,height:844});
  await guest.goto(host+qrPath);
  await expect(guest.locator('#guestPhoto')).toBeVisible();
  await expect(guest.locator('#guestDownload')).toBeVisible();
  expect(await guest.locator('main img').count()).toBe(1);
  await page.evaluate(async()=>{app.releaseHostCamera();await app.hostReleaseRequest;});
});
