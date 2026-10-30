import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

test('QR panel confirms first, retries QR alone afterwards, and reports missing public URL',async({page})=>{
  await page.addInitScript(()=>{
    Object.defineProperty(navigator,'mediaDevices',{value:{
      getUserMedia:async()=>{throw new Error('Fixture: denied');},enumerateDevices:async()=>[],
    }});
  });
  await page.route('https://fonts.googleapis.com/**',route=>route.fulfill({contentType:'text/css',body:''}));
  await page.goto('http://127.0.0.1:5183');
  await page.waitForFunction(()=>window.app?.isUsingSimulatedCamera);
  await page.waitForFunction(()=>app.sharingConfig?.configured);
  expect(await page.evaluate(()=>app.sharingConfig.local_only)).toBe(true);
  await page.evaluate(async()=>{
    app.fullAutoMode=false;app.goToScreen('capture');
    for(let i=0;i<6;i++) await app.captureCurrentFrameImmediately();
    await app.finishCaptureAndGoToResult();
  });
  expect(await page.evaluate(()=>app.serverSession.composite)).toBe(null);
  let uploads=0;
  page.on('request',request=>{if(request.method()==='PUT'&&request.url().endsWith('/composite'))uploads++;});
  let configured=false;
  await page.route('**/api/sessions/*/finalize',route=> configured ? route.fallback() : route.fulfill({
    status:503,contentType:'application/json',body:JSON.stringify({error:{message:'Chưa cấu hình PUBLIC_BASE_URL HTTPS công khai hợp lệ'}}),
  }));
  await page.locator('#confirmQRCodeBtn').click();
  await expect(page.locator('#sessionSaveStatus')).toHaveAttribute('data-state','saved');
  await expect(page.locator('#qrDescriptionText')).toContainText('PUBLIC_BASE_URL');
  expect(uploads).toBe(1);
  configured=true;
  await page.locator('#confirmQRCodeBtn').click();
  await expect(page.locator('#qrStatusBadge')).toContainText('QR sẵn sàng');
  const url=await page.locator('#qrExternalUrlInput').inputValue();
  expect(url).toMatch(/^http:\/\/localhost:8002\/p\/[A-Za-z0-9_-]{43}$/);
  await expect(page.locator('#qrLocalWarning')).toBeVisible();
  await expect(page.locator('#qrLocalWarning')).toContainText('điện thoại khác');
  expect(await page.locator('#qrCodeContainer img').evaluate(image=>image.naturalWidth)).toBeGreaterThan(0);
  await page.locator('#confirmQRCodeBtn').click();
  await expect(page.locator('#qrExternalUrlInput')).toHaveValue(url);
  expect(uploads).toBe(1);
  const state=await page.evaluate(()=>({share:app.activeShare}));
  const guest=await page.context().newPage();
  await guest.goto(url);
  await expect(guest.locator('#guestPhoto')).toBeVisible();
  const event=guest.waitForEvent('download');
  await guest.locator('#guestDownload').click();
  const downloaded=await event;
  expect(createHash('sha256').update(readFileSync(await downloaded.path())).digest('hex')).toBe(state.share.print_ready.sha256);
});

test('saving automatically loads QR without pressing the QR button or refreshing',async({page})=>{
  await page.addInitScript(()=>Object.defineProperty(navigator,'mediaDevices',{value:{getUserMedia:async()=>{throw new Error('Fixture');},enumerateDevices:async()=>[]}}));
  await page.route('https://fonts.googleapis.com/**',route=>route.fulfill({contentType:'text/css',body:''}));
  await page.goto('http://127.0.0.1:5183');
  await page.waitForFunction(()=>window.app?.isUsingSimulatedCamera);
  await page.evaluate(async()=>{
    app.fullAutoMode=false;app.goToScreen('capture');
    for(let i=0;i<6;i++)await app.captureCurrentFrameImmediately();
    await app.finishCaptureAndGoToResult();
  });
  await expect(page.locator('#qrReadyPill')).toHaveText('Chờ xác nhận ảnh');
  expect(await page.evaluate(()=>app.finalOperation)).toBe(null);
  await page.locator('#confirmSessionBtn').click();
  await expect(page.locator('#qrStatusBadge')).toContainText('QR sẵn sàng');
  await expect(page.locator('#qrLocalWarning')).toBeVisible();
  const url=await page.locator('#qrExternalUrlInput').inputValue();
  const guest=await page.context().newPage();
  await guest.goto(url);
  await expect(guest.locator('#guestPhoto')).toBeVisible();
});

test('QR PNG error never claims ready and retry preserves the saved share',async({page})=>{
  await page.addInitScript(()=>Object.defineProperty(navigator,'mediaDevices',{value:{getUserMedia:async()=>{throw new Error('Fixture');},enumerateDevices:async()=>[]}}));
  await page.route('https://fonts.googleapis.com/**',route=>route.fulfill({contentType:'text/css',body:''}));
  await page.goto('http://127.0.0.1:5183');
  await page.waitForFunction(()=>window.app?.isUsingSimulatedCamera);
  await page.evaluate(async()=>{
    app.fullAutoMode=false;app.goToScreen('capture');
    for(let i=0;i<6;i++)await app.captureCurrentFrameImmediately();
    await app.finishCaptureAndGoToResult();
  });
  let fail=true,finalizes=0;
  page.on('request',r=>{if(r.url().endsWith('/finalize'))finalizes++;});
  await page.route('**/p/*/qr.png',route=>fail ? route.fulfill({status:503,body:'QR fixture error'}) : route.fallback());
  await page.locator('#confirmQRCodeBtn').click();
  await expect(page.locator('#qrDescriptionText')).toContainText('không tải được file PNG QR');
  await expect(page.locator('#qrStatusBadge')).not.toContainText('QR sẵn sàng');
  expect(await page.evaluate(()=>app.saveState)).toBe('saved');
  const share=await page.evaluate(()=>app.activeShare.share_url);
  fail=false;
  await page.locator('#confirmQRCodeBtn').click();
  await expect(page.locator('#qrStatusBadge')).toContainText('QR sẵn sàng');
  expect(await page.locator('#qrExternalUrlInput').inputValue()).toBe(share);
  expect(finalizes).toBe(1);
});
