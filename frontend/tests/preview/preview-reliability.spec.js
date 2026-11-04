import {test,expect,request} from '@playwright/test';
let cookies;

test.beforeAll(async()=>{
  const api=await request.newContext({baseURL:'http://127.0.0.1:5188'});
  expect((await api.post('/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:'preview-only-disposable-pairing-key'}})).ok()).toBe(true);
  cookies=(await api.storageState()).cookies;await api.dispose();
});
test.beforeEach(async({page,context})=>{
  await context.addCookies(cookies);await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
});
test.afterEach(async({page})=>{await page.evaluate(async()=>{app.releaseHostCamera();await app.hostReleaseRequest;}).catch(()=>{});});

test('one dropped HTTP frame leaves countdown running and does not reconnect',async({page})=>{
  await page.locator('#timerBtn10').click();await page.locator('#setupStartCaptureBtn').click();
  await page.waitForFunction(()=>app.countdownState?.kind==='countdown');
  const epoch=await page.evaluate(()=>app.captureEpoch);let dropped=false,connects=0;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/camera/connect'))connects++;});
  await page.route('**/camera/frame',route=>{if(!dropped){dropped=true;return route.abort('connectionrefused');}return route.fallback();});
  const frames=await page.evaluate(()=>app.hostPreviewDiagnostics.frames);
  await expect.poll(()=>dropped).toBe(true);
  await page.waitForFunction(n=>app.hostPreviewDiagnostics.frames>n,frames);
  expect(await page.evaluate(()=>({paused:app.sequencePaused,running:app.isCapturingSequence,epoch:app.captureEpoch}))).toEqual({paused:false,running:true,epoch});
  expect(connects).toBe(0);
});

test('sustained loss pauses remaining countdown; recovery never resumes automatically or loses photos',async({page})=>{
  await page.evaluate(()=>app.capturePhoto(0));
  const photo=await page.evaluate(()=>app.photos[0].toDataURL());
  await page.locator('#timerBtn10').click();await page.locator('#setupStartCaptureBtn').click();
  await page.waitForFunction(()=>app.countdownState?.kind==='countdown');
  const epoch=await page.evaluate(()=>app.captureEpoch);let offline=true,captures=0,connects=0;
  page.on('request',r=>{if(r.url().endsWith('/camera/captures')&&r.method()==='POST')captures++;if(r.url().endsWith('/camera/connect')&&r.method()==='POST')connects++;});
  await page.route('**/camera/frame',r=>offline?r.abort('connectionrefused'):r.fallback());
  await page.waitForFunction(()=>app.sequencePaused&&app.isCapturingSequence);
  const remaining=await page.evaluate(()=>app.countdownState.remainingMs);
  expect(remaining).toBeGreaterThan(0);expect(remaining).toBeLessThan(10000);
  expect(await page.evaluate(()=>app.captureEpoch)).toBe(epoch);
  offline=false;await page.waitForFunction(()=>app.hostPreviewHealthy);
  expect(await page.evaluate(()=>app.sequencePaused)).toBe(true);
  expect(await page.evaluate(()=>app.countdownState.remainingMs)).toBe(remaining);
  expect(await page.evaluate(()=>app.photos[0].toDataURL())).toBe(photo);
  expect(captures).toBe(0);expect(connects).toBe(0);
  await page.locator('#mainCaptureBtn').click();await page.waitForFunction(()=>app.photos.filter(Boolean).length===2);
  expect(captures).toBe(1);
});

test('invalid image is diagnosed as browser decode failure, not USB loss',async({page})=>{
  let corrupt=true,connects=0;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/camera/connect'))connects++;});
  await page.route('**/camera/frame',async route=>{
    if(!corrupt)return route.fallback();
    await route.fulfill({status:200,headers:{'Content-Type':'image/jpeg','X-Frame-Sequence':String(Date.now()),'X-Frame-Time':String(Date.now()/1000),'X-Preview-Processing-Ms':'2.5'},body:'not a JPEG'});
  });
  await page.waitForFunction(()=>app.hostPreviewDiagnostics.lastFailure==='image_decode');
  expect(await page.evaluate(()=>app.hostCameraNeedsReconnect)).toBe(false);
  corrupt=false;
  await page.waitForFunction(()=>app.hostPreviewDiagnostics.lastFailure===null);
  expect(connects).toBe(0);
});

test('capture preflight may refresh preview while UI captureBusy is true',async({page})=>{
  const before=await page.evaluate(()=>app.hostPreviewDiagnostics.frames);
  await page.evaluate(async()=>{
    app.captureBusy=true;app.hostPreviewHealthy=false;
    try{await app.captureHostPhoto(0);}finally{app.captureBusy=false;}
  });
  expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(1);
  expect(await page.evaluate(()=>app.hostPreviewDiagnostics.frames)).toBeGreaterThan(before);
});

test('actual camera-disconnect recovery stops after three retries',async({page})=>{
  let connects=0;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/camera/connect'))connects++;});
  await page.route('**/camera/frame',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'disconnected',message:'TEST camera is unavailable',stage:'preview'}})}));
  await expect(page.locator('#hostCameraStatus')).toContainText('recovery stopped',{timeout:25000});
  expect(connects).toBe(3);
  expect(await page.evaluate(()=>app.hostPreviewTimer)).toBe(null);
  expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(0);
});

test('refresh while capture ACK is pending restores its key and never requests another shot',async({page})=>{
  let release;const hold=new Promise(resolve=>{release=resolve;});let saved=false;
  const keys=[];
  await page.route('**/camera/captures',async route=>{
    keys.push(route.request().headers()['idempotency-key']);
    const response=await route.fetch();
    if(keys.length===1){saved=true;await hold;}
    await route.fulfill({response}).catch(()=>{});
  });
  await page.evaluate(()=>{app.goToScreen('capture');});
  await page.locator('#manualInstantSnapBtn').click();
  await expect.poll(()=>saved).toBe(true);
  const pending=await page.evaluate(()=>app.hostCaptureOperation.key);
  // The original file is already saved. Recovering its ACK after reload must
  // still work if the physical camera can no longer connect.
  await page.route('**/camera/connect',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'disconnected',message:'TEST camera unplugged'}})}));
  await page.reload();release();
  await page.waitForFunction(()=>!!app.hostCaptureOperation&&!app.persistenceBusy);
  expect(await page.evaluate(()=>app.hostCaptureOperation.key)).toBe(pending);
  expect(await page.evaluate(()=>app.isCapturingSequence)).toBe(false);
  const photo=await page.evaluate(()=>app.photos[0].toDataURL());
  await page.locator('#retrySessionSaveBtn').click();
  await page.waitForFunction(()=>!app.hostCaptureOperation&&!app.captureBusy);
  expect(keys).toEqual([pending,pending]);
  expect(await page.evaluate(()=>app.serverSession.shots_revision)).toBe(1);
  expect(await page.evaluate(()=>app.photos[0].toDataURL())).toBe(photo);
  expect(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('amazing-race-session-v1')).cameraCapture)).toBe(undefined);
});

test('transfer error retries exactly the existing operation key',async({page})=>{
  const keys=[];
  await page.route('**/camera/captures',async route=>{
    keys.push(route.request().headers()['idempotency-key']);
    const response=await route.fetch();
    if(keys.length===1)return route.fulfill({status:504,contentType:'application/json',body:JSON.stringify({error:{code:'timeout',stage:'transfer',uncertain:false,message:'TEST transfer timeout'}})});
    await route.fulfill({response});
  });
  await page.evaluate(()=>app.goToScreen('capture'));await page.locator('#manualInstantSnapBtn').click();
  await expect(page.locator('#retrySessionSaveBtn')).toBeVisible();
  expect(await page.evaluate(()=>app.hostCaptureOperation.retryNewShot)).toBe(false);
  await page.locator('#retrySessionSaveBtn').click();await page.waitForFunction(()=>!app.hostCaptureOperation);
  expect(keys.length).toBe(2);expect(keys[0]).toBe(keys[1]);
  expect(await page.evaluate(()=>app.serverSession.shots_revision)).toBe(1);
});

test('pending transfer reconnects once with the same key without waiting for Live View',async({page})=>{
  const keys=[];let connects=0,previewAvailable=true;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/camera/connect'))connects++;});
  await page.route('**/camera/frame',r=>previewAvailable?r.fallback():r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'not_ready',message:'TEST preview paused during transfer'}})}));
  await page.route('**/camera/captures',async route=>{
    keys.push(route.request().headers()['idempotency-key']);
    if(keys.length===2)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'disconnected',stage:'transfer',uncertain:false,message:'TEST USB reconnect needed'}})});
    const response=await route.fetch();
    if(keys.length===1)return route.fulfill({status:504,contentType:'application/json',body:JSON.stringify({error:{code:'timeout',stage:'transfer',uncertain:false,message:'TEST transfer timeout'}})});
    await route.fulfill({response});
  });
  await page.evaluate(()=>app.goToScreen('capture'));await page.locator('#manualInstantSnapBtn').click();
  await expect(page.locator('#retrySessionSaveBtn')).toBeVisible();
  previewAvailable=false;
  await page.locator('#retrySessionSaveBtn').click();await page.waitForFunction(()=>!app.hostCaptureOperation);
  expect(keys.length).toBe(3);expect(new Set(keys).size).toBe(1);expect(connects).toBe(1);
  expect(await page.evaluate(()=>app.serverSession.shots_revision)).toBe(1);
});
