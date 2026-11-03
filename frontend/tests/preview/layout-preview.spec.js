import {test,expect,request as apiRequest} from '@playwright/test';
let pairedCookies,adminClient,adminCsrf;
test.beforeAll(async()=>{
  const client=await apiRequest.newContext({baseURL:'http://127.0.0.1:5188'});
  const response=await client.post('/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:'preview-only-disposable-pairing-key'}});
  expect(response.ok()).toBe(true);
  adminClient=await apiRequest.newContext({baseURL:'http://127.0.0.1:5188'});
  const login=await adminClient.post('/api/admin/login',{headers:{'X-OSA-Login':'1'},data:{username:'preview-host',password:process.env.AMAZING_RACE_PREVIEW_TEST_PASSWORD}});
  expect(login.ok()).toBe(true);adminCsrf=(await login.json()).csrf_token;
  const access=await adminClient.post('/api/admin/event-display/access',{headers:{'X-CSRF-Token':adminCsrf}});
  expect(access.ok()).toBe(true);
  const unlock=await client.post('/event-display/unlock',{headers:{'X-OSA-Display':'1'},data:{code:(await access.json()).code}});
  expect(unlock.ok()).toBe(true);pairedCookies=(await client.storageState()).cookies;await client.dispose();
});
test.afterAll(async()=>{await adminClient?.dispose();});
test.beforeEach(async({context,page})=>{
  await context.addCookies(pairedCookies);
  // Only the external HTTPS gateway is mocked here. Session persistence,
  // authorization, composite/footer generation and printing use the test API.
  await page.route('**/api/sessions/*/public-status',async route=>{
    const sid=new URL(route.request().url()).pathname.split('/')[3];
    const response=await page.request.get('/api/sessions/'+sid,{headers:{Authorization:route.request().headers().authorization}});
    const state=await response.json();await route.fulfill({json:{...state.share,public_ready:true,expires_at:new Date(Date.now()+86400000).toISOString()}});
  });
});
async function ready(page){await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);await expect(page.locator('#hostCameraPreview')).toBeVisible();}
for(const viewport of [{width:1024,height:768},{width:1180,height:820},{width:1366,height:1024},{width:768,height:1024},{width:390,height:844}])test(`compact guest viewport ${viewport.width}x${viewport.height}`,async({page})=>{
  await page.setViewportSize(viewport);await ready(page);
  const ids=['setupStartCaptureBtn','frameCardGrid2x3','frameCardLandscape4','timerBtn3','timerBtn5','timerBtn7','timerBtn10'];
  for(const id of ids)await expect(page.locator('#'+id)).toBeVisible();
  expect(await page.locator('#setupFrameChoices [role=radio]').count()).toBe(2);
  expect(await page.locator('#customFrameInputMain').count()).toBe(0);
  if(viewport.width>=960){
    expect(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1)).toBe(true);
    for(const id of ids){const box=await page.locator('#'+id).boundingBox();expect(box.y+box.height).toBeLessThanOrEqual(viewport.height);expect(box.height).toBeGreaterThanOrEqual(44);}
    await page.evaluate(()=>{const list=document.getElementById('recentPhotoList');for(let i=0;i<12;i++){const card=document.createElement('figure');card.style.minHeight='180px';list.append(card);}});
    expect(await page.locator('#recentPhotoList').evaluate(el=>el.scrollHeight>el.clientHeight&&getComputedStyle(el).overflowY==='auto')).toBe(true);
    expect(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1)).toBe(true);
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`test-results/preview/compact-${viewport.width}x${viewport.height}.png`,fullPage:true});
});
test.afterEach(async({page})=>{await page.evaluate(async()=>{app.releaseHostCamera();await app.hostReleaseRequest;}).catch(()=>{});});
test('layout switching keeps the same active preview, camera lease and timer',async({page})=>{
  const requests=[];
  page.on('request',r=>{if(r.method()==='POST'&&/\/camera\/(connect|disconnect|live-view\/start)$/.test(new URL(r.url()).pathname))requests.push(new URL(r.url()).pathname);});
  await ready(page);const sid=await page.evaluate(()=>app.sessionContext.id);
  await page.locator('#timerBtn7').click();
  for(const id of ['frameCardLandscape4','frameCardGrid2x3','frameCardLandscape4','frameCardGrid2x3','frameCardLandscape4']){
    const before=await page.evaluate(()=>app.hostFrameSequence);
    await page.locator('#'+id).click();
    await expect.poll(()=>page.evaluate(()=>app.hostPreviewHealthy&&app.hostFrameSequence>0)).toBe(true);
    await expect(page.locator('#hostCameraPreview')).toBeVisible();
    await expect.poll(()=>page.evaluate(()=>app.hostFrameSequence)).toBeGreaterThan(before);
    expect(await page.evaluate(()=>app.sessionContext.id)).toBe(sid);
    await expect.poll(()=>page.evaluate(()=>app.persistenceBusy)).toBe(false);
  }
  expect(requests.filter(path=>path.endsWith('/disconnect'))).toHaveLength(0);
  expect(requests.filter(path=>path.endsWith('/connect'))).toHaveLength(1);
  expect(await page.evaluate(()=>app.countdownSeconds)).toBe(7);
  expect(await page.evaluate(()=>[app.slotCount,app.presetLayout])).toEqual([4,'landscape_4']);
  await page.reload();await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  expect(await page.evaluate(()=>[app.slotCount,app.presetLayout])).toEqual([4,'landscape_4']);
});

for(const count of [4,6])test(`${count} shots: fullscreen, retake, Home preview, composite, QR/download/print`,async({page,context})=>{
  await page.setViewportSize({width:1024,height:768});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await ready(page);
  if(count===4){await page.locator('#frameCardLandscape4').click();await expect.poll(()=>page.evaluate(()=>app.persistenceBusy)).toBe(false);}
  await page.evaluate(()=>{app.fullAutoMode=false;app.countdownSeconds=1;app.goToScreen('capture');});
  await page.locator('#mainCaptureBtn').click();
  await expect(page.locator('body')).toHaveClass(/host-capture-fullscreen/);
  await expect.poll(()=>page.evaluate(()=>app.photos.filter(Boolean).length),{timeout:40000}).toBe(count);
  await expect.poll(()=>page.evaluate(()=>app.isCapturingSequence)).toBe(false);
  const original=await page.evaluate(()=>app.serverSession.photos.map(photo=>photo.id));
  await page.evaluate(()=>app.triggerSingleRetake(1));
  await page.locator('#mainCaptureBtn').click();
  await expect.poll(()=>page.evaluate(()=>app.serverSession.photos[1].id)).not.toBe(original[1]);
  expect(await page.evaluate(()=>app.serverSession.photos.filter(photo=>photo.slot_index!==1).map(photo=>photo.id))).toEqual(original.filter((_,index)=>index!==1));
  await expect.poll(()=>page.evaluate(()=>app.isCapturingSequence)).toBe(false);
  await page.evaluate(()=>app.goToScreen('home'));
  await expect(page.locator('#hostCameraPreview')).toBeVisible();
  const sequence=await page.evaluate(()=>app.hostFrameSequence);
  await expect.poll(()=>page.evaluate(()=>app.hostFrameSequence)).toBeGreaterThan(sequence);
  // Used-session layout changes must not corrupt the selected slots/metadata.
  await page.evaluate(count=>app.selectPresetLayout(count===4?'grid2x3':'landscape_4'),count);
  expect(await page.evaluate(()=>app.slotCount)).toBe(count);
  await page.evaluate(()=>{app.guestWorkflowActive=true;app.finishCaptureAndGoToResult(true);});
  await expect(page.locator('#screenResult')).toBeVisible();
  for(const id of ['compositeCanvas','confirmSessionBtn','guestReviewShots']){
    const box=await page.locator('#'+id).boundingBox();expect(box.y+box.height).toBeLessThanOrEqual(768);
  }
  expect(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1)).toBe(true);
  await page.screenshot({path:`test-results/preview/compact-review-${count}.png`});
  expect(await page.locator('#compositeCanvas').evaluate(canvas=>[canvas.width,canvas.height])).toEqual(count===4?[1800,1200]:[1200,1800]);
  await expect(page.locator('#eventDisplayConsent,#eventDisplayConsentLabel')).toHaveCount(0);
  page.once('dialog',dialog=>dialog.dismiss());await page.locator('#newSessionButton').click();
  await expect(page.locator('#screenResult')).toBeVisible();
  expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(count);
  await expect(page.getByRole('button',{name:/Khách tiếp theo/})).toHaveCount(0);
  await expect(page.locator('#confirmSessionBtn')).toHaveText('Confirm, Display Photo & Get QR');
  const projector=await context.newPage();await projector.goto('/event-display');
  await expect(projector.locator('#displayPresentation')).toBeVisible();
  expect((await projector.request.get('/api/admin/sessions')).status()).toBe(401);
  let editedPixels;
  if(count===4){
    const originalPreview=await page.locator('#compositeCanvas').evaluate(canvas=>canvas.toDataURL());
    await page.locator('#filterGridContainer button').nth(3).click();
    await page.locator('#tabBtn_stickers').click();
    await page.locator('#stickerItemsGrid button').first().click();
    await page.locator('#tabBtn_color').click();
    await page.locator('#colorSwatchesGrid button').nth(2).click();
    await page.locator('#tabBtn_text').click();
    await page.locator('#inputTopText').fill('PIPELINE AUDIT');
    expect(await page.locator('#compositeCanvas').evaluate(canvas=>canvas.toDataURL())).not.toBe(originalPreview);
    editedPixels=await page.locator('#compositeCanvas').evaluate(async canvas=>{
      const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
      return [...new Uint8Array(await crypto.subtle.digest('SHA-256',pixels))].map(n=>n.toString(16).padStart(2,'0')).join('');
    });
  }
  await page.locator('#confirmSessionBtn').click();
  await expect(page.locator('#qrCodeContainer')).toHaveAttribute('data-phase','ready');
  if(editedPixels){
    const persistedPixels=await page.evaluate(async()=>{
      const response=await fetch(`/api/sessions/${app.sessionContext.id}/composites/${app.finalOperation.compositeId}/image`,{headers:{Authorization:`Bearer ${app.sessionContext.token}`}});
      if(!response.ok)throw new Error('Official composite is unavailable');
      const image=await createImageBitmap(await response.blob());
      const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
      const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);image.close();
      const pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data;
      return [...new Uint8Array(await crypto.subtle.digest('SHA-256',pixels))].map(n=>n.toString(16).padStart(2,'0')).join('');
    });
    expect(persistedPixels).toBe(editedPixels);
  }
  expect(await page.evaluate(()=>app.finalOperation.editor.event_display_consent)).toBe(true);
  expect(await page.evaluate(()=>app.finalOperation.editor.event_display_consent_source)).toBe('confirmation_projection_qr_v1');
  await expect.poll(()=>page.locator('#recentPhotoList img').count()).toBeGreaterThan(0);
  await expect(projector.locator('#photoWall figure[data-photo-id]')).toHaveCount(1);
  const publishedId=await page.locator('#recentPhotoList img').first().getAttribute('data-display-id');
  await expect(projector.locator('#photoWall figure[data-photo-id]')).toHaveAttribute('data-photo-id',publishedId);
  await expect(page.locator('#qrExpiryMessage')).toHaveText('Your QR code expires in 24 hours.');
  await expect(page.locator('#qrDescriptionText')).toBeHidden();
  await expect(page.locator('#guestDeliveryPanel button,#guestDeliveryPanel input,#guestDeliveryPanel a,#qrStatusBadge,#qrReadyPill,#qrConnectionMode')).toHaveCount(0);
  for(const selector of ['#qrCodeContainer','#printPhotoBtn','#guestDeliveryActions button[onclick="app.downloadCompositeImage()"]','#newSessionButton']){
    const box=await page.locator(selector).boundingBox();expect(box.y+box.height).toBeLessThanOrEqual(768);
  }
  await page.screenshot({path:`test-results/preview/compact-delivery-${count}.png`});
  const link=await page.evaluate(()=>app.activeShare.share_url);
  expect((await page.request.get(new URL(link).pathname)).ok()).toBeTruthy();
  expect((await page.request.get(new URL(link).pathname+'/download')).ok()).toBeTruthy();
  await page.locator('#printPhotoBtn').click();await expect(page.locator('#printStatus')).toContainText('Mock printer received');
  const publishedSession=await page.evaluate(()=>app.sessionContext.id);
  await page.locator('#newSessionButton').click();await expect(page.locator('#screenHome')).toBeVisible();
  await expect(page.locator('#setupStartCaptureBtn')).toBeEnabled();
  await expect(page.locator('#recentPhotoList img')).toHaveCount(1);
  const hidden=await adminClient.put('/api/admin/event-display/photos/'+publishedSession,{headers:{'X-CSRF-Token':adminCsrf},data:{approved:false}});
  expect(hidden.ok()).toBe(true);
  await expect(projector.locator('#photoWall figure[data-photo-id]')).toHaveCount(0);
  await expect(page.locator('#recentPhotoList img')).toHaveCount(0);await projector.close();
  expect(errors).toEqual([]);
});

test('temporary backend frame failure hides stale preview then reconnects without duplicate loops',async({page})=>{
  await ready(page);await page.locator('#frameCardLandscape4').click();
  await expect.poll(()=>page.evaluate(()=>app.persistenceBusy)).toBe(false);
  let offline=true;
  await page.route('**/camera/frame',route=>offline?route.abort('connectionrefused'):route.fallback());
  await expect.poll(()=>page.evaluate(()=>app.hostPreviewHealthy)).toBe(false);
  await expect(page.locator('#hostCameraPreview')).toBeHidden();
  offline=false;
  await page.waitForFunction(()=>app.hostPreviewHealthy);
  const initial=await page.evaluate(()=>app.hostFrameSequence);
  await expect.poll(()=>page.evaluate(()=>app.hostFrameSequence)).toBeGreaterThan(initial);
  let connects=0;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/camera/connect'))connects++;});
  await page.evaluate(()=>Promise.all([app.prepareHostCamera(),app.prepareHostCamera(),app.prepareHostCamera()]));
  expect(connects).toBe(0);
  expect(await page.locator('#hostCameraPreview').evaluate(image=>getComputedStyle(image).objectFit)).toBe('contain');
});

test('layout change during an in-flight connection keeps one camera connection and clean release',async({page})=>{
  let release;const wait=new Promise(resolve=>{release=resolve;});let connects=0,disconnects=0,frames=0;
  page.on('request',r=>{
    if(r.method()==='POST'&&r.url().endsWith('/camera/connect'))connects++;
    if(r.method()==='POST'&&r.url().endsWith('/camera/disconnect'))disconnects++;
    if(r.url().endsWith('/camera/frame'))frames++;
  });
  await page.route('**/camera/connect',async route=>{await wait;await route.fallback();});
  await page.goto('/');await page.waitForFunction(()=>window.app?.hostConnectRequest&&app.sessionContext?.id);
  await page.locator('#frameCardLandscape4').click();
  await expect.poll(()=>page.evaluate(()=>app.persistenceBusy)).toBe(false);
  release();await page.waitForFunction(()=>app.hostPreviewHealthy);
  expect(connects).toBe(1);expect(disconnects).toBe(0);
  expect(await page.evaluate(()=>[app.serverSession.slot_count,app.sessionContext.layout])).toEqual([4,'landscape_4']);
  await page.evaluate(async()=>{app.releaseHostCamera();await app.hostReleaseRequest;});
  const stoppedFrames=frames;
  await page.waitForTimeout(2500); // Exceed the automatic reconnect delay.
  expect(frames).toBe(stoppedFrames);expect(connects).toBe(1);expect(disconnects).toBe(1);
  await expect(page.locator('#hostCameraPreview')).toBeHidden();
});

test('Drive upload pending hides QR and automatically retries only the confirmed composite',async({page})=>{
  await ready(page);await page.locator('#frameCardLandscape4').click();
  await expect.poll(()=>page.evaluate(()=>app.persistenceBusy)).toBe(false);
  await page.evaluate(()=>{app.countdownSeconds=1;});
  let synced=false,finalizes=0,composites=0;
  page.on('request',request=>{if(request.method()==='PUT'&&request.url().endsWith('/composite'))composites++;});
  await page.route('**/finalize',async route=>{
    finalizes++;
    if(!synced)return route.fulfill({status:503,json:{error:{message:'Ảnh đã lưu an toàn; đang chờ đồng bộ Google Drive.'}}});
    return route.fallback();
  });
  await page.locator('#setupStartCaptureBtn').click();
  await expect(page.locator('body')).toHaveAttribute('data-workflow','review',{timeout:40000});
  expect(finalizes).toBe(0);
  await page.locator('#confirmSessionBtn').click();
  await expect(page.locator('#qrCodeContainer')).toHaveAttribute('data-phase','processing');
  await expect(page.locator('#qrCodeContainer img')).toHaveCount(0);
  expect(composites).toBe(1);
  synced=true;
  await expect(page.locator('#qrCodeContainer')).toHaveAttribute('data-phase','ready',{timeout:15000});
  expect(composites).toBe(1);expect(finalizes).toBeGreaterThan(1);
});
