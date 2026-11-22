import {test,expect,request as apiRequest} from '@playwright/test';
import {existsSync,readFileSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
let pairedCookies,adminClient,adminCsrf;
test.beforeAll(async()=>{
  const client=await apiRequest.newContext({baseURL:'http://127.0.0.1:5188'});
  const response=await client.post('/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:'preview-only-disposable-pairing-key'}});
  expect(response.ok()).toBe(true);
  adminClient=await apiRequest.newContext({baseURL:'http://127.0.0.1:5188'});
  const login=await adminClient.post('/api/admin/login',{headers:{'X-OSA-Login':'1'},data:{username:'preview-host',password:process.env.AMAZING_RACE_PREVIEW_TEST_PASSWORD}});
  expect(login.ok()).toBe(true);adminCsrf=(await login.json()).csrf_token;
  pairedCookies=(await client.storageState()).cookies;await client.dispose();
});
test.afterAll(async()=>{await adminClient?.dispose();});
test.beforeEach(async({context,page})=>{
  await context.addCookies(pairedCookies);
  // Only the external HTTPS gateway is mocked here. Session persistence,
  // authorization, composite/footer generation and printing use the test API.
  await page.route('**/api/sessions/*/public-status',async route=>{
    const sid=new URL(route.request().url()).pathname.split('/')[3];
    const response=await page.request.get(new URL('/api/sessions/'+sid,route.request().url()).href,{headers:{Authorization:route.request().headers().authorization}});
    const state=await response.json();await route.fulfill({json:{...state.share,public_ready:true,expires_at:new Date(Date.now()+86400000).toISOString()}});
  });
});
async function ready(page){await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);await expect(page.locator('#hostCameraPreview')).toBeVisible();}
async function verifyRetainedStickerRendering(page, canvas) {
  const originalPreview=await canvas.evaluate(value=>value.toDataURL());
  await expect(page.locator('#stickerItemsGrid')).toHaveCount(0);
  await page.evaluate(()=>app.addEmojiSticker('⭐'));
  expect(await canvas.evaluate(value=>value.toDataURL())).not.toBe(originalPreview);
}
for(const viewport of [
  {width:1024,height:768},{width:1180,height:820},{width:1366,height:700},{width:1366,height:768},
  {width:1920,height:1080},{width:768,height:1024},{width:360,height:800},
  {width:390,height:844},{width:430,height:932},
])test(`compact guest viewport ${viewport.width}x${viewport.height}`,async({page})=>{
  await page.setViewportSize(viewport);await ready(page);
  const ids=['setupStartCaptureBtn','frameCardGrid2x3','frameCardLandscape4','timerBtn3','timerBtn5','timerBtn7','timerBtn10'];
  for(const id of ids)await expect(page.locator('#'+id)).toBeVisible();
  await expect(page.locator('#boothHeader .font-display-title,#boothHeader .official-event-brand')).toHaveCount(0);
  await expect(page.locator('#boothHeader')).not.toContainText('📸');
  await expect(page.locator('#setupStartCaptureBtn')).toHaveText('Start Capturing');
  await expect(page.getByRole('heading',{name:'Choose a Photo Layout'})).toHaveCount(0);
  expect(await page.locator('#setupFrameChoices [role=radio]').count()).toBe(2);
  expect(await page.locator('#customFrameInputMain').count()).toBe(0);
  if(viewport.width>=960){
    const live=await page.locator('#setupPreviewMount').boundingBox();
    expect(live.height).toBeGreaterThan(viewport.height*.54);
    expect((await page.locator('#setupOptions').boundingBox()).height).toBeLessThan(100);
    expect(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1)).toBe(true);
    for(const id of ids){const box=await page.locator('#'+id).boundingBox();expect(box.y+box.height).toBeLessThanOrEqual(viewport.height);expect(box.height).toBeGreaterThanOrEqual(44);}
    await page.evaluate(()=>{const list=document.getElementById('recentPhotoList');for(let i=0;i<12;i++){const card=document.createElement('figure');card.style.minHeight='180px';list.append(card);}});
    expect(await page.locator('#recentPhotoList').evaluate(el=>el.scrollHeight>el.clientHeight&&getComputedStyle(el).overflowY==='auto')).toBe(true);
    expect(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1)).toBe(true);
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const artwork=await page.evaluate(()=>getComputedStyle(document.body,'::before').backgroundImage);
  expect(artwork).toContain('Theme-ptb-final');
  const themeUrl=artwork.slice(5,-2);
  expect((await page.request.get(themeUrl)).ok()).toBe(true);
  const logoArea=await page.locator('#boothHeader').boundingBox();
  const preview=await page.locator('#setupPreviewMount').boundingBox();
  expect(preview.y).toBeGreaterThanOrEqual(logoArea.y+logoArea.height);
  if(viewport.width===768)expect(preview.height).toBeGreaterThan(460);
  await page.screenshot({path:`test-results/preview/compact-${viewport.width}x${viewport.height}.png`,fullPage:true});
});
test.afterEach(async({page})=>{
  await page.evaluate(async()=>{app.releaseHostCamera();await app.hostReleaseRequest;}).catch(()=>{});
  await page.unrouteAll({behavior:'ignoreErrors'});
});
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
  test.setTimeout(160000);
  await page.setViewportSize({width:1024,height:768});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://127.0.0.1:8028/booth');
  await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  if(count===4){await page.locator('#frameCardLandscape4').click();await expect.poll(()=>page.evaluate(()=>app.persistenceBusy)).toBe(false);}
  await page.evaluate(()=>{app.fullAutoMode=false;app.countdownSeconds=1;app.goToScreen('capture');});
  await page.locator('#mainCaptureBtn').click();
  await expect(page.locator('body')).toHaveClass(/host-capture-fullscreen/);
  expect((await page.locator('#cameraPreviewPanel').boundingBox()).y).toBeGreaterThanOrEqual(51);
  await expect(page.locator('body')).toHaveCSS('--booth-theme',/Theme-ptb-final/);
  await expect.poll(()=>page.evaluate(()=>app.photos.filter(Boolean).length),{timeout:65000}).toBe(count);
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
  await expect(page.locator('body')).toHaveCSS('--booth-theme',/Theme-ptb-final/);
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
  await expect(page.locator('#confirmSessionBtn')).toHaveText('Confirm & Display');
  const projector=await context.newPage();await projector.goto('http://127.0.0.1:8028/event-display');
  await expect(projector.locator('#displayPresentation')).toBeVisible();
  await expect(projector.locator('#displayLogin')).toBeHidden();
  expect((await projector.request.get('/api/admin/sessions')).status()).toBe(401);
  const canvas=page.locator('#compositeCanvas');
  await verifyRetainedStickerRendering(page, canvas);
  const editedPixels=await canvas.evaluate(async value=>{
    const pixels=value.getContext('2d').getImageData(0,0,value.width,value.height).data;
    return [...new Uint8Array(await crypto.subtle.digest('SHA-256',pixels))].map(n=>n.toString(16).padStart(2,'0')).join('');
  });
  await page.locator('#confirmSessionBtn').click();
  await expect.poll(()=>page.evaluate(()=>Boolean(app.serverSession?.finalized)),{timeout:30000}).toBe(true);
  {
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
  await expect(page.locator('#qrCodeContainer')).toHaveAttribute('data-phase','ready',{timeout:30000});
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
  await page.locator('#printPhotoBtn').click();await expect(page.locator('#printStatus')).toHaveText('Test print request received.');
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

for(const count of [4,6])test(`official frame fills ${count} openings and saves the exact preview`,async({page})=>{
  test.skip(process.env.TEST_AMAZING_RACE_FRAMES!=='1','Requires the two installed Host frame PNGs');
  const layout=count===4?'landscape_4':'grid2x3';
  const frameFile=new URL(`../../../runtime/frames/custom-${layout}.png`,import.meta.url);
  expect(existsSync(frameFile)).toBe(true);
  const base='http://127.0.0.1:8028';
  await page.goto(base+'/booth');
  await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  if(count===4)await page.locator('#frameCardLandscape4').click();
  await expect.poll(()=>page.evaluate(()=>app.serverSession?.slot_count)).toBe(count);
  const context=await page.evaluate(()=>({id:app.sessionContext.id,token:app.sessionContext.token}));
  const sessionURL=base+'/api/sessions/'+context.id;
  const auth={Authorization:'Bearer '+context.token};
  const me=await page.request.get(base+'/api/booth/me');
  const csrf=(await me.json()).csrf_token;
  for(let slot=0;slot<count;slot++){
    const png=await page.evaluate(slot=>{
      const canvas=document.createElement('canvas');canvas.width=120;canvas.height=80;
      const ctx=canvas.getContext('2d');
      ctx.fillStyle=`hsl(${slot*47},85%,45%)`;ctx.fillRect(0,0,120,80);
      return canvas.toDataURL().split(',')[1];
    },slot);
    const upload=await page.request.post(sessionURL+'/photos',{
      headers:{...auth,'X-Booth-CSRF':csrf,'Idempotency-Key':randomUUID()},
      multipart:{slot_index:String(slot),source:'demo',file:{name:'fixture.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')}},
    });
    expect(upload.ok()).toBe(true);
  }
  await page.reload();
  await expect(page.locator('#confirmSessionBtn')).toBeEnabled();
  await expect(page.locator('#guestReviewShots button')).toHaveCount(count);
  const measured=await page.evaluate(async ({layout,src})=>{
    const frame=new Image();frame.src=src;await frame.decode();
    app.hostFrames[layout]={image:frame,slot_count:app.slotCount,slots:[],pad_x:6,pad_top:7,pad_bottom:15,gap:3};
    app.applyConfiguredHostFrame();
    app.renderCompositeCanvas();
    const canvas=document.getElementById('compositeCanvas'),width=canvas.width,height=canvas.height;
    const mask=document.createElement('canvas');mask.width=width;mask.height=height;
    const maskCtx=mask.getContext('2d');maskCtx.drawImage(frame,0,0,width,height);
    const artwork=maskCtx.getImageData(0,0,width,height).data;
    const output=canvas.getContext('2d').getImageData(0,0,width,height).data;
    let uncovered=0,changedArtwork=0;
    for(let i=0;i<artwork.length;i+=4){
      if(artwork[i+3]===0&&output[i]===30&&output[i+1]===64&&output[i+2]===175)uncovered++;
      if(artwork[i+3]===255&&[0,1,2].some(offset=>Math.abs(artwork[i+offset]-output[i+offset])>2))changedArtwork++;
    }
    return {count:app.detectedSlots?.length,uncovered,changedArtwork};
  },{layout,src:'data:image/png;base64,'+readFileSync(frameFile).toString('base64')});
  expect(measured).toMatchObject({count,uncovered:0,changedArtwork:0});
  const preview=page.locator('#compositeCanvas');
  await verifyRetainedStickerRendering(page, preview);
  const previewPixels=await preview.evaluate(async canvas=>{
    const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
    return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',pixels)));
  });
  await page.locator('#confirmSessionBtn').click();
  let finalized;
  // Verify the persisted final, independently of asynchronous delivery/QR.
  await expect.poll(async()=>{
    const response=await page.request.get(sessionURL,{headers:auth});
    if(response.ok())finalized=await response.json();
    return Boolean(finalized?.finalized);
  },{timeout:20000}).toBe(true);
  const savedPixels=await page.evaluate(async ({id,token,composite})=>{
    const response=await fetch(`/api/sessions/${id}/composites/${composite}/image`,{headers:{Authorization:'Bearer '+token}});
    if(!response.ok)throw new Error('Official composite is unavailable');
    const photo=await createImageBitmap(await response.blob());
    const canvas=document.createElement('canvas');canvas.width=photo.width;canvas.height=photo.height;
    const ctx=canvas.getContext('2d');ctx.drawImage(photo,0,0);photo.close();
    return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',ctx.getImageData(0,0,canvas.width,canvas.height).data)));
  },{...context,composite:finalized.composite.id});
  expect(savedPixels).toEqual(previewPixels);
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

test('temporary sharing error hides QR and retries only the confirmed composite',async({page})=>{
  await ready(page);await page.locator('#frameCardLandscape4').click();
  await expect.poll(()=>page.evaluate(()=>app.persistenceBusy)).toBe(false);
  await page.evaluate(()=>{app.countdownSeconds=1;});
  let sharingAvailable=false,finalizes=0,composites=0;
  page.on('request',request=>{if(request.method()==='PUT'&&request.url().endsWith('/composite'))composites++;});
  await page.route('**/finalize',async route=>{
    finalizes++;
    if(!sharingAvailable)return route.fulfill({status:503,json:{error:{message:'Test sharing service unavailable.'}}});
    return route.fallback();
  });
  await page.locator('#setupStartCaptureBtn').click();
  await expect(page.locator('body')).toHaveAttribute('data-workflow','review',{timeout:40000});
  expect(finalizes).toBe(0);
  await page.locator('#confirmSessionBtn').click();
  await expect(page.locator('#qrCodeContainer')).toHaveAttribute('data-phase','error');
  await expect(page.locator('#qrCodeContainer img')).toHaveCount(0);
  expect(composites).toBe(1);
  sharingAvailable=true;
  await expect(page.locator('#qrCodeContainer')).toHaveAttribute('data-phase','ready',{timeout:15000});
  expect(composites).toBe(1);expect(finalizes).toBeGreaterThan(1);
});

test('Host saves both frames independently and Booth uses the matching artwork', async ({page,context}) => {
  const makeFrame = async (width,height,color) => Buffer.from(await page.evaluate(({width,height,color}) => {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.clearRect(80,130,width-160,height-260);
    return canvas.toDataURL().split(',')[1];
  },{width,height,color}),'base64');
  const portrait = await makeFrame(960,1440,'#1a5276');
  const landscape = await makeFrame(1440,960,'#1e8450');
  await context.addCookies((await adminClient.storageState()).cookies);
  await page.goto('http://127.0.0.1:8028/admin#frames');
  await expect(page.locator('#frameList article')).toHaveCount(3);
  await page.locator('#frameManagement summary').click();
  const layout = page.locator('#frameLayout');
  const preview = page.locator('#framePreview');
  async function configure(id,name,buffer,pad) {
    await layout.selectOption(id);
    await page.locator('#frameUpload').setInputFiles({name,mimeType:'image/png',buffer});
    await expect(preview).toHaveAttribute('src',new RegExp('layout='+id));
    await page.locator('#framePadX').fill(String(pad));
    await page.locator('#saveFrameConfig').click();
    await expect(page.locator('#frameManagementStatus')).toContainText('bố cục đã chọn');
    await expect(layout).toBeEnabled();
  }
  const headers = {'X-CSRF-Token': adminCsrf};
  try {
    await configure('grid2x3','custom-portrait.png',portrait,8);
    await configure('landscape_4','custom-landscape.png',landscape,12);
    await expect(page.locator('#frameList img')).toHaveCount(2);
    await layout.selectOption('grid2x3');
    await expect(page.locator('#frameName')).toHaveValue('custom-portrait.png');
    await expect(page.locator('#framePadX')).toHaveValue('8');
    await expect(preview).toHaveAttribute('src',/layout=grid2x3/);

    await ready(page);
    await expect(page.locator('body')).toHaveAttribute('data-event-mode', 'false');
    await expect(page.locator('#frameCardGrid2x3 .host-frame-preview')).toBeVisible();
    await expect(page.locator('#frameCardLandscape4 .host-frame-preview')).toBeVisible();
    const rendered = () => page.evaluate(() => {
      app.renderCompositeCanvas();
      const canvas = document.getElementById('compositeCanvas');
      return [canvas.width, canvas.height, ...canvas.getContext('2d').getImageData(10, 10, 1, 1).data];
    });
    await page.locator('#frameCardLandscape4').click();
    await expect.poll(() => page.evaluate(() => app.serverSession?.slot_count)).toBe(4);
    expect(await rendered()).toEqual([1440,960,30,132,80,255]);

    await page.reload();
    await expect.poll(() => page.evaluate(() => app.serverSession?.slot_count)).toBe(4);
    expect(await page.evaluate(() => app.slotMetrics.padX)).toBe(12);
    expect(await rendered()).toEqual([1440,960,30,132,80,255]);
    await page.locator('#frameCardGrid2x3').click();
    await expect.poll(() => page.evaluate(() => app.serverSession?.slot_count)).toBe(6);
    expect(await page.evaluate(() => app.slotMetrics.padX)).toBe(8);
    expect(await rendered()).toEqual([960,1440,26,82,118,255]);
  } finally {
    for (const [layout,slot_count] of [['grid2x3',6],['landscape_4',4]]) {
      await adminClient.put('/api/admin/frames/custom', {headers, data: {layout,slot_count,enabled:false}});
    }
  }
});
