import {test,expect,request} from '@playwright/test';

let cookies;
test.beforeAll(async()=>{
  const api=await request.newContext({baseURL:'http://127.0.0.1:5188'});
  expect((await api.post('/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:'preview-only-disposable-pairing-key'}})).ok()).toBe(true);
  cookies=(await api.storageState()).cookies;await api.dispose();
});
test.afterEach(async({page})=>{
  await page.evaluate(async()=>{app.releaseHostCamera();await app.hostReleaseRequest;}).catch(()=>{});
});

for(const count of [4,6])test(`QR recovers after HTTPS outage, ${count} saved photos, without duplicate finalize`,async({page,context})=>{
  await context.addCookies(cookies);await page.goto('/');
  await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  await page.locator(count===4?'#frameCardLandscape4':'#frameCardGrid2x3').click();
  await page.evaluate(async count=>{
    for(let slot=0;slot<count;slot++)await app.capturePhoto(slot);
    app.guestWorkflowActive=true;app.goToScreen('result');
  },count);
  let outage=true,finalizes=0,prefer;
  page.on('request',req=>{
    if(req.url().endsWith('/finalize')){finalizes++;prefer=req.headers().prefer;}
  });
  // Only the external proof is simulated. Persistence, token and QR PNG are real.
  await page.route('**/public-status',async route=>{
    if(outage)return route.fulfill({status:503,json:{error:{message:'Disposable external HTTPS outage'}}});
    const share=await page.evaluate(()=>app.activeShare);
    await route.fulfill({json:{...share,public_ready:true,expires_at:new Date(Date.now()+86400000).toISOString()}});
  });
  const started=Date.now();await page.locator('#confirmSessionBtn').click();
  await page.waitForFunction(()=>app.activeShare&&!app.shareBusy&&!app.persistenceBusy);
  await expect(page.locator('#qrCodeContainer')).toHaveAttribute('data-phase','error');
  await expect(page.locator('#qrCodeContainer')).not.toContainText('Could not create QR code');
  const token=await page.evaluate(()=>app.activeShare.share_url.split('/p/')[1]);
  outage=false;await page.evaluate(()=>app.refreshPublicQR());
  await expect(page.locator('#qrCodeContainer')).toHaveAttribute('data-phase','ready');
  const elapsed=Date.now()-started;
  await page.locator('#qrCodeContainer img').evaluate(img=>{window.readyQRImage=img;});
  await page.evaluate(()=>app.refreshPublicQR());
  expect(await page.evaluate(()=>document.querySelector('#qrCodeContainer img')===window.readyQRImage)).toBe(true);
  expect(await page.evaluate(()=>app.activeShare.share_url.split('/p/')[1])).toBe(token);
  expect(finalizes).toBe(1);expect(prefer).toBe('respond-async');
  expect(await page.evaluate(()=>app.serverSession.status)).toBe('completed');
  outage=true;
  await page.evaluate(async()=>{app.qrRetryFailures=11;await app.refreshPublicQR();});
  await expect(page.getByRole('button',{name:'Retry sharing',exact:true})).toBeEnabled();
  outage=false;await page.getByRole('button',{name:'Retry sharing',exact:true}).click();
  await expect(page.locator('#qrCodeContainer')).toHaveAttribute('data-phase','ready');
  expect(await page.evaluate(()=>app.activeShare.share_url.split('/p/')[1])).toBe(token);
  console.log(`Confirm → displayed QR (${count} photos, simulated HTTPS recovery): ${elapsed} ms`);
});
