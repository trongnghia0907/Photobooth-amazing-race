import {test,expect,request} from '@playwright/test';
let cookies;
test.use({actionTimeout:10000});
test.beforeAll(async()=>{
  const api=await request.newContext({baseURL:'http://127.0.0.1:5188'});
  const response=await api.post('/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:'preview-only-disposable-pairing-key'}});
  expect(response.ok()).toBe(true);cookies=(await api.storageState()).cookies;await api.dispose();
});

for(const count of [4,6])test(`paused manual ${count} photos: Complete opens existing Review without confirming`,async({page,context})=>{
  await context.addCookies(cookies);await page.setViewportSize({width:1024,height:768});
  let captures=0,confirmations=0;
  page.on('request',r=>{
    if(r.method()==='POST'&&r.url().endsWith('/camera/captures'))captures++;
    if(['POST','PUT'].includes(r.method())&&/\/(composite|complete|finalize|print-jobs)$/.test(new URL(r.url()).pathname))confirmations++;
  });
  await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  if(count===4){await page.locator('#frameCardLandscape4').click();await expect.poll(()=>page.evaluate(()=>app.persistenceBusy)).toBe(false);}
  await page.locator('#setupStartCaptureBtn').click();
  await expect(page.locator('#mainCaptureBtnText')).toHaveText('Tạm dừng');
  await page.locator('#mainCaptureBtn').click();
  await expect(page.locator('#countdownOverlay')).toBeHidden();
  for(let index=0;index<count;index++){
    await expect(page.locator('#completeCaptureBtn')).toBeHidden();
    await page.locator('#manualInstantSnapBtn').click();
    await expect(page.locator('#capturedCountBadge')).toHaveText(`${index+1} / ${count} complete`);
    await expect(page.locator('#manualInstantSnapBtn')).toBeEnabled();
  }
  await expect(page.locator('#completeCaptureBtn')).toBeVisible();
  await expect(page.locator('#completeCaptureBtn')).toBeEnabled();
  expect(await page.evaluate(()=>app.sequencePaused)).toBe(true);
  const before=await page.evaluate(()=>({ids:app.serverSession.photos.map(p=>p.id),images:app.photos.map(p=>p.toDataURL())}));
  await page.waitForTimeout(1200);await expect(page.locator('#screenCapture')).toBeVisible();
  await page.locator('#completeCaptureBtn').evaluate(button=>{button.click();button.click();});
  await expect(page.locator('#screenResult')).toBeVisible();await expect(page.locator('#confirmSessionBtn')).toBeVisible();
  expect(await page.evaluate(()=>({ids:app.serverSession.photos.map(p=>p.id),images:app.photos.map(p=>p.toDataURL())}))).toEqual(before);
  expect(await page.evaluate(()=>app.serverSession.finalized)).toBe(false);
  expect(captures).toBe(count);expect(confirmations).toBe(0);
  expect(await page.evaluate(()=>!app.countdownTimerId&&!app.sequenceTimerId&&!app.countdownState)).toBe(true);
});
for(const count of [4,6])test(`compact pause control: ${count} photos and automatic review`,async({page,context})=>{
  await context.addCookies(cookies);await page.setViewportSize({width:1024,height:768});
  let finalizations=0;page.on('request',r=>{if(r.method()==='POST'&&/\/(complete|finalize)$/.test(r.url()))finalizations++;});
  await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  if(count===4){await page.locator('#frameCardLandscape4').click();await expect.poll(()=>page.evaluate(()=>app.persistenceBusy)).toBe(false);}
  await page.locator('#timerBtn3').click();await page.locator('#setupStartCaptureBtn').click();
  await expect(page.locator('#countdownNumber')).toHaveText('2');
  await page.locator('#mainCaptureBtn').click();await expect(page.locator('#mainCaptureBtnText')).toHaveText('Tiếp tục chụp');
  await expect(page.locator('body')).not.toHaveClass(/host-capture-fullscreen/);
  await expect(page.locator('#mainCaptureBtn')).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('#hostCaptureExit')).toHaveCount(0);
  await expect(page.locator('#capturedCountBadge')).toHaveText(`0 / ${count} complete`);
  await expect(page.locator('#manualInstantSnapBtn')).toBeVisible();await expect(page.locator('#resetAllShotsBtn')).toBeVisible();
  await expect(page.locator('#countdownOverlay')).toBeHidden();
  const remaining=await page.locator('#countdownNumber').textContent();await page.waitForTimeout(1300);
  await expect(page.locator('#countdownNumber')).toHaveText(remaining);expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(0);
  await page.locator('#mainCaptureBtn').click();await expect(page.locator('#mainCaptureBtnText')).toHaveText('Tạm dừng');
  await expect(page.locator('body')).toHaveAttribute('data-workflow','review',{timeout:45000});
  expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(count);
  expect(await page.evaluate(()=>app.serverSession.finalized)).toBe(false);expect(finalizations).toBe(0);
  await expect(page.locator('#guestReviewShots button')).toHaveCount(count);
  await expect(page.locator('#confirmSessionBtn')).toBeVisible();
  expect(await page.evaluate(()=>!app.countdownTimerId&&!app.sequenceTimerId&&!app.countdownState)).toBe(true);
  const before=await page.evaluate(()=>app.serverSession.photos.map(p=>p.id));
  let release;const connected=new Promise(resolve=>{release=resolve;});
  await page.route('**/camera/connect',async route=>{await connected;await route.fallback();});
  await page.locator('#guestReviewShots button').nth(1).click();
  await expect(page.locator('#screenCapture')).toBeVisible();
  await page.waitForFunction(()=>!!app.hostConnectRequest,{},{timeout:10000});
  expect(await page.evaluate(()=>app.isCapturingSequence)).toBe(false);
  release();await page.waitForFunction(()=>app.hostPreviewHealthy);
  expect(await page.evaluate(()=>!app.isCapturingSequence&&!app.countdownTimerId&&!app.sequenceTimerId)).toBe(true);
  expect(await page.evaluate(()=>app.serverSession.photos.map(p=>p.id))).toEqual(before);
  await page.locator('#cancelRetakeBtn').click();await expect(page.locator('#screenResult')).toBeVisible();
  expect(await page.evaluate(()=>app.serverSession.photos.map(p=>p.id))).toEqual(before);
  await page.unroute('**/camera/connect');
  await page.locator('#guestReviewShots button').nth(1).click();await page.waitForFunction(()=>app.hostPreviewHealthy);
  await page.locator('#mainCaptureBtn').click();await expect(page.locator('#screenResult')).toBeVisible({timeout:20000});
  const retaken=await page.evaluate(()=>app.serverSession.photos.map(p=>p.id));expect(retaken[1]).not.toBe(before[1]);
  expect(retaken.filter((_,i)=>i!==1)).toEqual(before.filter((_,i)=>i!==1));
  await page.locator('#guestReviewShots button').last().click();await page.locator('#manualInstantSnapBtn').click();
  await expect(page.locator('#screenResult')).toBeVisible({timeout:15000});
  const instant=await page.evaluate(()=>app.serverSession.photos.map(p=>p.id));expect(instant[count-1]).not.toBe(retaken[count-1]);
  expect(instant.slice(0,-1)).toEqual(retaken.slice(0,-1));expect(finalizations).toBe(0);
});
