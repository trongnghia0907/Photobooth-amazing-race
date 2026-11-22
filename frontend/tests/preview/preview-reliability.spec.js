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

test('pending capture shows stage progress without competing preview or duplicate shutter',async({page})=>{
  let release;const held=new Promise(resolve=>release=resolve);let polls=0,captures=0,frames=0,connects=0;
  page.on('request',request=>{
    if(request.url().endsWith('/camera/frame'))frames++;
    if(request.url().endsWith('/camera/connect'))connects++;
  });
  await page.route('**/camera/status',route=>{
    polls++;
    return route.fulfill({json:{capture_progress:{capture_id:'simulated-capture',stage:'receiving_original'},
      camera_progress:{capture_id:'simulated-capture',stage:'waiting_buffer'}}});
  });
  await page.route('**/camera/captures',async route=>{
    captures++;const response=await route.fetch();await held;await route.fulfill({response}).catch(()=>{});
  });
  try{
    await page.evaluate(()=>app.goToScreen('capture'));
    await page.locator('#manualInstantSnapBtn').click();
    await expect.poll(()=>polls).toBeGreaterThanOrEqual(1);const before=frames,checked=polls;
    await expect.poll(()=>polls).toBeGreaterThan(checked);
    await expect(page.locator('#hostCameraStatus')).toHaveText('Waiting for the original JPEG from the camera…');
    expect(frames).toBe(before);expect(captures).toBe(1);expect(connects).toBe(0);
    release();await page.waitForFunction(()=>app.photos.filter(Boolean).length===1&&!app.captureBusy);
    expect(captures).toBe(1);
  }finally{release();}
});

test('actual camera-disconnect recovery stops after three retries',async({page})=>{
  let connects=0;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/camera/connect'))connects++;});
  await page.route('**/camera/frame',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'disconnected',message:'TEST camera is unavailable',stage:'preview'}})}));
  await expect(page.locator('#hostCameraStatus')).toContainText('Camera disconnected',{timeout:25000});
  await expect.poll(()=>connects,{timeout:25000}).toBe(3);
  await expect.poll(()=>page.evaluate(()=>app.hostCameraState)).toBe('disconnected');
  expect(await page.evaluate(()=>app.hostPreviewTimer)).toBe(null);
  expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(0);
});

test('a hard WIA error reopens preview once without taking a photo',async({page})=>{
  let connects=0,captures=0,injected=false;
  page.on('request',request=>{
    if(request.url().endsWith('/camera/connect'))connects++;
    if(request.url().endsWith('/camera/captures'))captures++;
  });
  await page.route('**/camera/frame',route=>{
    if(injected)return route.fallback();
    injected=true;
    return route.fulfill({status:503,json:{error:{code:'transport_failed',message:'WIA root failed',stage:'preview'}}});
  });
  await expect.poll(()=>connects).toBe(1);
  await page.waitForFunction(()=>app.hostPreviewHealthy);
  expect(connects).toBe(1);
  expect(captures).toBe(0);
});

test('an unresolved receipt reports that no new shutter was sent and keeps the key',async({page})=>{
  const keys=[];
  await page.route('**/camera/captures',route=>{
    keys.push(route.request().headers()['idempotency-key']);
    return route.fulfill({status:503,json:{error:{code:'camera_recovery_pending',stage:'transfer',shutter_dispatched:false,
      message:'The previous Sony capture is unresolved.'}}});
  });
  await page.evaluate(()=>app.goToScreen('capture'));
  await page.locator('#manualInstantSnapBtn').click();
  await expect.poll(()=>page.evaluate(()=>app.persistenceError)).toBe(
    'The previous Sony capture is unresolved. No new shutter command was sent.');
  await expect(page.locator('#capturedCountBadge')).toHaveText('0 / 6 complete');
  await page.locator('#retrySessionSaveBtn').click();
  await expect.poll(()=>keys.length).toBe(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[1]).toBe(keys[0]);
});

test('proven preflight failure clears retry state without changing saved photos',async({page})=>{
  let captures=0;
  await page.route('**/camera/captures',route=>{
    captures++;
    return route.fulfill({status:503,json:{error:{code:'camera_mode',stage:'capture',
      shutter_dispatched:false,clear_pending:true,message:'Use Single Shooting.'}}});
  });
  await page.evaluate(()=>app.goToScreen('capture'));
  await page.locator('#manualInstantSnapBtn').click();
  await expect.poll(()=>page.evaluate(()=>!app.hostCaptureOperation&&!app.captureBusy)).toBe(true);
  expect(await page.evaluate(()=>app.persistenceError)).toBe('');
  await expect(page.locator('#capturedCountBadge')).toHaveText('0 / 6 complete');
  expect(captures).toBe(1);
});

test('missing WIA device explains USB checks and stops automatic reconnects',async({page})=>{
  let connects=0;
  await page.route('**/camera/connect',route=>{
    connects++;
    return route.fulfill({status:503,json:{error:{code:'wia_device_unavailable',stage:'connect',
      message:'Check Device Manager and your USB data cable.'}}});
  });
  await page.route('**/camera/frame',route=>route.fulfill({status:503,json:{error:{code:'disconnected',stage:'preview'}}}));
  await expect(page.locator('#hostCameraStatus')).toHaveText('Check Device Manager and your USB data cable.');
  expect(await page.evaluate(()=>app.hostPreviewTimer)).toBe(null);
  expect(connects).toBe(1);
});

test('Booth Camera uses the Host and blocks an abandoned receipt before countdown',async({page})=>{
  let captures=0;
  page.on('request',request=>{if(request.url().endsWith('/camera/captures'))captures++;});
  await page.route(url=>url.pathname.endsWith('/camera/status')&&url.searchParams.get('check_capture')==='true',
    route=>route.fulfill({status:503,json:{error:{code:'camera_recovery_pending',stage:'capture',
      message:'Camera capture is blocked by an earlier shot.',shutter_dispatched:false}}}));
  expect(await page.evaluate(()=>app.cameraSource)).toBe('host');
  await page.locator('#setupStartCaptureBtn').click();
  await expect(page.locator('#setupCameraStatus')).toHaveText('Camera capture is blocked by an earlier shot.');
  expect(await page.evaluate(()=>app.currentScreen)).toBe('home');
  expect(await page.evaluate(()=>app.countdownState)).toBe(null);
  await expect(page.locator('#retrySessionSaveBtn')).toBeHidden();
  expect(captures).toBe(0);
});

test('Retry Save loads the same saved slot without submitting another shot',async({page})=>{
  const posts=[];let failImage=true;
  page.on('request',request=>{
    if(request.url().endsWith('/camera/captures'))posts.push({
      key:request.headers()['idempotency-key'],data:request.postDataJSON()});
  });
  await page.route('**/photos/*/image',route=>{
    if(!failImage)return route.fallback();
    failImage=false;
    return route.fulfill({status:503});
  });
  await page.evaluate(()=>app.goToScreen('capture'));
  await page.locator('#manualInstantSnapBtn').click();
  await expect(page.locator('#sessionSaveStatus')).toContainText('Photo saved on Host.');
  await expect(page.locator('#capturedCountBadge')).toHaveText('0 / 6 complete');
  await page.locator('#retrySessionSaveBtn').click();
  await expect(page.locator('#capturedCountBadge')).toHaveText('1 / 6 complete');
  expect(posts).toEqual([{key:posts[0].key,data:{slot_index:0}},
    {key:posts[0].key,data:{slot_index:0,recovery_only:true}}]);
  expect(await page.evaluate(()=>app.serverSession.photos.map(photo=>photo.slot_index))).toEqual([0]);
});

test('a busy connection stops visibly and can be retried in the same session',async({page})=>{
  let busy=true,connects=0,captures=0;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/camera/captures'))captures++;});
  await page.route('**/camera/connect',route=>{
    connects++;
    return busy?route.fulfill({status:409,json:{error:{code:'busy',message:'WIA busy',stage:'connect'}}}):route.fallback();
  });
  await page.evaluate(async()=>{app.releaseHostCamera();await app.hostReleaseRequest;await app.prepareHostCamera().catch(()=>{});});
  const id=await page.evaluate(()=>app.sessionContext.id);
  await expect(page.locator('#hostCameraStatus')).toHaveText('Camera is busy. Select Start Capturing to retry.',{timeout:25000});
  expect(connects).toBe(4);
  expect(await page.evaluate(()=>app.hostPreviewTimer)).toBe(null);
  busy=false;
  await page.evaluate(()=>app.prepareHostCamera());
  await expect(page.locator('#hostCameraPreview')).toBeVisible();
  expect(await page.evaluate(()=>app.sessionContext.id)).toBe(id);
  expect(captures).toBe(0);
});

test('persistent preview busy stops polling and manual reconnect reuses the lease',async({page})=>{
  let busy=true,frames=0,connects=0;
  page.on('request',r=>{if(r.url().endsWith('/camera/connect'))connects++;});
  await page.route('**/camera/frame',route=>{
    frames++;
    return busy?route.fulfill({status:409,json:{error:{code:'busy',message:'WIA busy'}}}):route.fallback();
  });
  await expect(page.locator('#hostCameraStatus')).toContainText('Camera unavailable',{timeout:18000});
  expect(await page.evaluate(()=>app.hostPreviewDiagnostics.busyFrames)).toBe(6);
  expect(frames).toBeGreaterThanOrEqual(6);
  expect(await page.evaluate(()=>app.hostPreviewTimer)).toBe(null);
  busy=false;
  await page.evaluate(()=>app.prepareHostCamera());
  await page.waitForFunction(()=>app.hostPreviewHealthy);
  expect(connects).toBe(0);
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
