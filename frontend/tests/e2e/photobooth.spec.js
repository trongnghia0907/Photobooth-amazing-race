import { test, expect } from '@playwright/test';
import { readFileSync, mkdirSync, readdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const evidence = fileURLToPath(new URL('../../../docs/screenshots/', import.meta.url));
mkdirSync(evidence,{recursive:true});
const distAssets = new URL('../../dist/assets/', import.meta.url);
const cssFile = readdirSync(distAssets).find(n=>n.endsWith('.css'));
const compiledCSS = readFileSync(new URL(cssFile, distAssets),'utf8');
const portOffset=Number(process.env.OSA_TEST_PORT_OFFSET || 0);
const localUrl=port=>`http://127.0.0.1:${port+portOffset}`;

async function setup(page, url=localUrl(5173), expectMock=true) {
  const errors=[], externalWrites=[], missing=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  page.on('response',r=>{if(r.status()===404)missing.push(r.url());});
  await page.route('**/*',async route=>{
    const req=route.request(), target=req.url();
    if (/^https?:/.test(target) && !target.startsWith('http://127.0.0.1:')) {
      if(req.method()!=='GET')externalWrites.push(target);
      if(target.includes('tailwindcss.com')) return route.fulfill({contentType:'application/javascript',body:'window.tailwind = {};'});
      if(target.includes('fonts.googleapis.com')) return route.fulfill({contentType:'text/css',body:''});
      if(target.includes('qrcode.min.js')) return route.fulfill({contentType:'application/javascript',body:''});
      return route.fulfill({status:200,body:''});
    }
    if(target.includes(':5513')) {externalWrites.push(target);return route.fulfill({body:''});}
    return route.continue();
  });
  await page.addInitScript(()=>{
    // Deterministic denied preview permissions; no physical camera or print dialog.
    Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{
      getUserMedia:async()=>{throw new Error('Test: camera denied');},
      enumerateDevices:async()=>[{kind:'videoinput',deviceId:'fixture-camera',label:'Fixture preview'}]
    }});
    window.printCalls=0;
    window.print=()=>window.printCalls++;
  });
  await page.goto(url);
  // Legacy const app is intentionally lexical, modular facade is window.app.
  if(expectMock) await page.waitForFunction(()=>typeof app!=='undefined' && app.isUsingSimulatedCamera);
  else await page.waitForSelector('#demoModeBadge');
  if(new URL(url).port===String(5174+portOffset)) {
    await page.addStyleTag({content:compiledCSS});
    await page.evaluate(()=>{app.autoPrintPopup=false;app.fullAutoMode=false;app.generateQRCodeForCurrentPhoto=async()=>{};app.triggerHardwareCameraShutter=async()=>{};});
  }
  return {errors,externalWrites,missing};
}

async function fixture(page, frame=false) {
  const data=await page.evaluate(frame=>{
    const c=document.createElement('canvas');c.width=300;c.height=450;
    const x=c.getContext('2d');x.fillStyle=frame?'#1E40AF':'#ff9977';x.fillRect(0,0,300,450);
    if(frame)for(let r=0;r<3;r++)for(let col=0;col<2;col++)x.clearRect(18+col*136,32+r*115,127,105);
    return c.toDataURL('image/png').split(',')[1];
  },frame);
  return {name:frame?'six-holes.png':'fixture.png',mimeType:'image/png',buffer:Buffer.from(data,'base64')};
}

test('Home/setup, timers, mock selector, mirror, no technical guest controls and delayed-start cancellation', async({page})=>{
  const log=await setup(page);
  await expect(page.locator('#screenHome')).toBeVisible();
  for(const n of [3,5,7,10]) {
    await page.locator(`#timerBtn${n}`).click();
    await expect(page.locator('#timerHintText')).toHaveText(`${n} giây / tấm`);
  }
  await page.locator('#homeCameraSelect').selectOption('fixture-camera');
  await page.locator('#homeCameraSelect').selectOption('simulated_camera');
  await page.locator('#homeMirrorBtn').click();
  expect(await page.evaluate(()=>app.mirrorVideo)).toBe(false);
  await expect(page.locator('#settingsModal')).toHaveCount(0);
  await expect(page.locator('#kioskExtraControls')).toHaveCount(0);
  await expect(page.locator('#setupLayoutChoices > .layout-choice-card')).toHaveCount(2);
  await expect(page.locator('#customFrameInputMain, #frameCardGrid3x2')).toHaveCount(0);
  await page.locator('#frameCardLandscape4').click();
  expect(await page.evaluate(()=>app.slotCount)).toBe(4);
  await page.locator('#frameCardGrid2x3').click();
  expect(await page.evaluate(()=>app.slotCount)).toBe(6);
  expect(await page.evaluate(()=>app.fullAutoMode)).toBe(true);
  await expect(page.locator('#slotDetectStatus')).toHaveCount(0);
  await page.screenshot({path:evidence+'modular-home.png'});
  await page.clock.install();
  await page.evaluate(()=>{app.startAutomaticSession();app.goToScreen('home');});
  await page.clock.fastForward(2000);
  expect(await page.evaluate(()=>app.isCapturingSequence)).toBe(false);
  expect(log).toEqual({errors:[],externalWrites:[],missing:[]});
});

test('countdown six shots, pause/resume, dynamic slot retake/delete, reset and automatic result', async({page})=>{
  const log=await setup(page);
  await page.evaluate(()=>{app.fullAutoMode=false;app.setCountdownSeconds(3);app.goToScreen('capture');});
  await page.clock.install();
  await page.locator('#mainCaptureBtn').click();
  await expect(page.locator('#countdownOverlay')).toBeVisible();
  await page.locator('#mainCaptureBtn').click();
  await page.clock.fastForward(4000);
  expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(0);
  await page.locator('#mainCaptureBtn').click();
  for(let i=0;i<6;i++){
    await page.clock.runFor(3000);
    await expect.poll(()=>page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(i+1);
    await page.clock.fastForward(950);
  }
  await expect(page.locator('#capturedCountBadge')).toHaveText('6 / 6 hoàn tất');
  await page.screenshot({path:evidence+'modular-capture.png'});
  for(const slot of [1,4]) {
    await page.locator('#sixSlotsGrid > div').nth(slot).click();
    expect(await page.evaluate(()=>app.singleRetakeIndex)).toBe(slot);
    await page.clock.runFor(3000);
    await expect.poll(()=>page.evaluate(()=>app.singleRetakeIndex)).toBe(null);
  }
  await page.locator('#sixSlotsGrid > div').nth(1).locator('button').dispatchEvent('click');
  await expect(page.locator('#goToResultBtn')).toBeDisabled();
  await expect.poll(()=>page.evaluate(()=>app.pendingDeletion===null&&app.photos.filter(Boolean).length===5)).toBe(true);
  expect(await page.evaluate(()=>app.isCapturingSequence)).toBe(false);
  await page.locator('#manualInstantSnapBtn').click();
  await expect(page.locator('#goToResultBtn')).toBeEnabled();
  await page.locator('#goToResultBtn').click();
  await expect(page.locator('#screenResult')).toBeVisible();
  await expect(page.locator('#qrStatusBadge')).toContainText('DEMO');
  await expect(page.locator('#qrExternalOpenBtn')).not.toHaveAttribute('href');
  await page.evaluate(async()=>{app.goToScreen('capture');await app.resetSessionShots();app.fullAutoMode=true;});
  for(let i=0;i<6;i++) {
    await page.locator('#manualInstantSnapBtn').click();
    await expect.poll(()=>page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(i+1);
  }
  await page.clock.runFor(4000);
  await expect(page.locator('#screenResult')).toBeVisible();
  expect(await page.evaluate(()=>window.printCalls)).toBe(0);
  await page.evaluate(()=>{app.fullAutoMode=false;app.startNewGuestSession();});
  await expect(page.locator('#screenHome')).toBeVisible();
  expect(await page.evaluate(()=>app.photos.every(p=>p===null)&&app.placedStickers.length===0)).toBe(true);
  expect(log).toEqual({errors:[],externalWrites:[],missing:[]});
});

test('all filters/categories, stickers mouse/touch, text, download and print boundary',async({page})=>{
  const log=await setup(page);
  const photo=await fixture(page);
  await page.evaluate(()=>{app.fullAutoMode=false;app.goToScreen('capture');});
  await page.locator('input[multiple]').setInputFiles(Array.from({length:6},(_,i)=>({...photo,name:`fixture-${i}.png`})));
  await expect(page.locator('#goToResultBtn')).toBeEnabled();
  await page.locator('#goToResultBtn').click();
  await page.evaluate(()=>app.selectPresetLayout('grid3x2'));
  expect(await page.locator('#compositeCanvas').evaluate(c=>[c.width,c.height])).toEqual([1800,1200]);
  await page.evaluate(()=>app.selectPresetLayout('grid2x3'));
  expect(await page.locator('#compositeCanvas').evaluate(c=>[c.width,c.height])).toEqual([1200,1800]);
  for(let i=0;i<9;i++) {
    await page.locator('#filterGridContainer button').nth(i).click();
    expect(await page.evaluate(()=>app.selectedFilter)).toBe(await page.evaluate(i=>app.filters[i].id,i));
  }
  await page.locator('#tabBtn_stickers').click();
  for(let i=0;i<4;i++) {
    await page.locator('#stickerCategoryBar button').nth(i).click();
    await page.locator('#stickerItemsGrid button').first().click();
  }
  await page.locator('#tabPanel_stickers input[type=file]').setInputFiles(photo);
  await page.waitForFunction(()=>app.placedStickers.length===5);
  await page.evaluate(()=>{app.placedStickers.forEach((s,i)=>{s.x=.1+i*.18;s.y=.5;});app.renderCompositeCanvas();});
  const box=await page.locator('#compositeCanvas').boundingBox();
  await page.mouse.move(box.x+box.width*.1,box.y+box.height*.5);await page.mouse.down();
  await page.mouse.move(box.x+box.width*.16,box.y+box.height*.56);await page.mouse.up();
  expect(await page.evaluate(()=>app.placedStickers[0].x)).toBeGreaterThan(.12);
  // Exercise the retained touch listener with real DOM Touch events.
  await page.locator('#compositeCanvas').evaluate(c=>{
    const r=c.getBoundingClientRect(),s=app.placedStickers[1];
    const touch=(x,y)=>new Touch({identifier:1,target:c,clientX:r.left+r.width*x,clientY:r.top+r.height*y});
    c.dispatchEvent(new TouchEvent('touchstart',{touches:[touch(s.x,s.y)],cancelable:true,bubbles:true}));
    window.dispatchEvent(new TouchEvent('touchmove',{touches:[touch(.4,.6)],cancelable:true}));
    window.dispatchEvent(new TouchEvent('touchend',{touches:[]}));
  });
  expect(await page.evaluate(()=>app.placedStickers[1].x)).toBeCloseTo(.4,1);
  await page.locator('#tabBtn_color').click();
  await page.locator('#colorSwatchesGrid button').nth(5).click();
  await page.locator('#customColorPicker').fill('#123456');
  await page.locator('#tabBtn_text').click();
  await page.locator('#inputTopText').fill('AR TEST');
  await page.locator('#inputCardTitle').fill('Refactor test');
  await page.locator('#inputBrandingText').fill('Fixture only');
  expect(await page.evaluate(()=>app.customTexts.topText)).toBe('AR TEST');
  await page.evaluate(()=>app.openMobilePreviewModal());
  await expect(page.locator('#mobileModalImage')).toHaveAttribute('src',/^data:image\/png/);
  await page.locator('#mobilePreviewModal button').last().click();
  const downloadEvent=page.waitForEvent('download');
  await page.getByText('TẢI ẢNH VỀ',{exact:true}).click();
  expect((await downloadEvent).suggestedFilename()).toMatch(/^amazing-race-2026-.*\.png$/);
  await page.evaluate(()=>app.triggerPrint());
  await expect(page.locator('#toastContainer')).toContainText('Xác nhận & Tạo QR');
  await page.evaluate(()=>app.showToast('Regression fixture','info'));
  await expect(page.locator('#toastContainer')).toContainText('Regression fixture');
  await page.screenshot({path:evidence+'modular-result.png'});
  await page.evaluate(()=>app.clearAllStickers());
  expect(await page.evaluate(()=>app.placedStickers.length)).toBe(0);
  await page.waitForTimeout(100);
  expect(await page.evaluate(()=>window.printCalls)).toBe(0);
  expect(log).toEqual({errors:[],externalWrites:[],missing:[]});
});

test('baseline screenshots and pixel-identical compositor output for all filters and both presets',async({page,context})=>{
  const baseline=await context.newPage();
  await setup(baseline,localUrl(5174));
  await setup(page);
  const currentBranding=await page.evaluate(()=>app.customTexts);
  await baseline.evaluate(texts=>{app.customTexts=texts;},currentBranding);
  await baseline.screenshot({path:evidence+'legacy-home.png'});
  for(const p of [baseline,page]) {
    await p.evaluate(()=>{
      app.fullAutoMode=false;app.autoPrintPopup=false;
      app.photos=Array.from({length:6},(_,i)=>{
        const c=document.createElement('canvas');c.width=960;c.height=720;
        const x=c.getContext('2d');x.fillStyle=['red','green','blue','orange','purple','pink'][i];x.fillRect(0,0,960,720);return c;
      });
      app.goToScreen('capture');
    });
  }
  await baseline.screenshot({path:evidence+'legacy-capture.png'});
  for(const layout of ['grid2x3','grid3x2']) for(const filter of ['normal','bw','vintage','warm','cool','dramatic','fade','vivid','sepia']) {
    const render=async p=>p.evaluate(({layout,filter})=>{
      app.presetLayout=layout;app.selectedFilter=filter;app.renderCompositeCanvas();
      return document.getElementById('compositeCanvas').toDataURL();
    },{layout,filter});
    expect(await render(page)).toBe(await render(baseline));
  }
  await baseline.evaluate(()=>app.goToScreen('result'));
  await baseline.screenshot({path:evidence+'legacy-result.png'});
});

test('built artifact loads on iPad portrait/landscape with functional dynamic handlers',async({page})=>{
  const log=await setup(page,localUrl(4173));
  for(const viewport of [{width:820,height:1180},{width:1180,height:820}]) {
    await page.setViewportSize(viewport);
    await page.evaluate(()=>{app.goToScreen('result');app.selectFilter('vivid');app.switchCustomTab('stickers');});
    await page.locator('#stickerItemsGrid button').first().click();
    await page.screenshot({path:evidence+`modular-ipad-${viewport.width}.png`});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  expect(log).toEqual({errors:[],externalWrites:[],missing:[]});
});

test('production artifact refuses simulated and video-frame capture',async({page})=>{
  const log=await setup(page,localUrl(4273),false);
  await expect(page.locator('#demoModeBadge')).toContainText('Chưa hỗ trợ production');
  const result=await page.evaluate(()=>{
    const messages=[];
    for(const run of [()=>app.startSimulatedCamera(),()=>app.captureFrameIntoSlot(0),()=>app.handleManualPhotoFilesUpload({target:{files:[]}})]) {
      try {run();} catch(e) {messages.push(e.message);}
    }
    return {messages,photos:app.photos.filter(Boolean).length,stream:app.stream};
  });
  expect(result.messages).toHaveLength(3);
  expect(result.photos).toBe(0);
  expect(result.stream).toBe(null);
  expect(log).toEqual({errors:[],externalWrites:[],missing:[]});
});

test('real backend: explicit composite confirmation, retake metadata, private files and repeat confirmation',async({page})=>{
  const log=await setup(page);
  await page.evaluate(async()=>{app.fullAutoMode=false;await app.prepareSession();app.goToScreen('capture');});
  const sid=await page.evaluate(()=>app.sessionContext.id);
  expect(sid).toMatch(/^[a-f0-9-]{36}$/);
  const photo=await fixture(page);
  await page.locator('input[multiple]').setInputFiles(Array.from({length:6},(_,i)=>({...photo,name:`saved-${i}.png`})));
  await expect(page.locator('#goToResultBtn')).toBeEnabled();
  // Retake remains available until final confirmation.
  await page.evaluate(()=>{app.singleRetakeIndex=1;});
  await page.locator('#manualInstantSnapBtn').click();
  await expect.poll(()=>page.evaluate(()=>app.serverSession.photos[1].revision)).toBe(2);
  await page.locator('#goToResultBtn').click();
  expect(await page.evaluate(()=>app.serverSession.composite)).toBe(null);
  await page.locator('#filterGridContainer button').nth(3).click();
  expect(await page.evaluate(()=>app.serverSession.composite)).toBe(null);
  await page.locator('#confirmSessionBtn').click();
  await expect(page.locator('#sessionSaveStatus')).toHaveAttribute('data-state','saved');
  let state=await page.evaluate(()=>app.serverSession);
  expect(state.status).toBe('completed');
  expect(state.photos.filter((_,i)=>i!==1).map(p=>p.source)).toEqual(Array(5).fill('manual_upload'));
  const firstComposite=state.composite.id;
  const storage=new URL('../../../.tools/e2e-backend/',import.meta.url);
  expect(existsSync(new URL('photobooth.sqlite3',storage))).toBe(true);
  expect(readdirSync(new URL(`originals/${sid}/`,storage))).toHaveLength(0);
  expect(readdirSync(new URL(`composites/${sid}/`,storage))).toHaveLength(1);
  await page.locator('#confirmSessionBtn').click();
  await expect.poll(()=>page.evaluate(()=>app.persistenceBusy)).toBe(false);
  expect(readdirSync(new URL(`composites/${sid}/`,storage))).toHaveLength(1);
  await expect(page.locator('#tabPanel_filters')).toHaveAttribute('inert','');
  await expect(page.locator('[id^="stepNav"]')).toHaveCount(0);
  await expect(page.locator('#finalPhotoNotice')).toBeVisible();
  expect(readdirSync(new URL(`composites/${sid}/`,storage))).toHaveLength(1);
  state=await page.evaluate(()=>app.serverSession);
  expect(state.composite.id).toBe(firstComposite);
  expect(state.finalized).toBe(true);
  expect(await page.evaluate(()=>app.photos.every(p=>p===null))).toBe(true);
  expect(readdirSync(new URL(`originals/${sid}/`,storage))).toHaveLength(0);
  const access=await page.evaluate(async()=>{
    const s=app.serverSession,c=app.sessionContext;
    const path=`/api/sessions/${c.id}/composites/${s.composite.id}/image`;
    const unauthorized=await fetch(path);
    const authorized=await fetch(path,{headers:{Authorization:`Bearer ${c.token}`}});
    return {unauthorized:unauthorized.status,authorized:authorized.status,size:(await authorized.blob()).size};
  });
  expect(access.unauthorized).toBe(401);
  expect(access.authorized).toBe(200);
  expect(access.size).toBeGreaterThan(1000);
  // The deliberately unauthorized GET emits a browser HTTP error; it is tested above.
  expect(log.externalWrites).toEqual([]);
  expect(log.missing).toEqual([]);
});

test('backend failures: pending shots survive, retry reuses keys, final upload and complete responses may be lost',async({page})=>{
  const log=await setup(page);
  await page.evaluate(()=>{app.fullAutoMode=false;app.goToScreen('capture');});
  let failPhotos=true;
  await page.route('**/api/sessions/*/photos',async route=>{
    if(failPhotos) return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{message:'Backend đang mất kết nối (test)'}})});
    return route.fallback();
  });
  const photo=await fixture(page);
  await page.locator('input[multiple]').setInputFiles(Array.from({length:6},(_,i)=>({...photo,name:`pending-${i}.png`})));
  await expect(page.locator('#sessionSaveStatus')).toHaveAttribute('data-state','error');
  expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(0);
  expect(await page.evaluate(()=>app.pendingPhotos.filter(Boolean).length)).toBe(6);
  const keys=await page.evaluate(()=>app.pendingPhotos.map(p=>p.key));
  failPhotos=false;
  await page.locator('#retrySessionSaveBtn').click();
  await expect(page.locator('#goToResultBtn')).toBeEnabled();
  expect(await page.evaluate(()=>app.pendingPhotos.every(p=>p===null))).toBe(true);
  expect(await page.evaluate(()=>app.serverSession.photos.every(p=>p.revision===1))).toBe(true);
  const sid=await page.evaluate(()=>app.sessionContext.id);
  const storage=new URL('../../../.tools/e2e-backend/',import.meta.url);
  expect(readdirSync(new URL(`originals/${sid}/`,storage))).toHaveLength(6);
  expect(keys.every(Boolean)).toBe(true);
  await page.locator('#goToResultBtn').click();
  let loseComposite=true,loseComplete=true;
  await page.route('**/api/sessions/*/composite',async route=>{
    const response=await route.fetch();
    if(loseComposite){loseComposite=false;return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{message:'Mất phản hồi sau lưu composite (test)'}})});}
    return route.fulfill({response});
  });
  await page.route('**/api/sessions/*/complete',async route=>{
    const response=await route.fetch();
    if(loseComplete){loseComplete=false;return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{message:'Mất phản hồi sau complete (test)'}})});}
    return route.fulfill({response});
  });
  await page.locator('#confirmSessionBtn').click();
  await expect(page.locator('#sessionSaveStatus')).toHaveAttribute('data-state','error');
  expect(readdirSync(new URL(`composites/${sid}/`,storage))).toHaveLength(1);
  await page.locator('#retrySessionSaveBtn').click();
  await expect(page.locator('#sessionSaveStatus')).toContainText('Mất phản hồi sau complete');
  expect(await page.evaluate(()=>app.saveState)).not.toBe('saved');
  await page.locator('#retrySessionSaveBtn').click();
  await expect(page.locator('#sessionSaveStatus')).toHaveAttribute('data-state','saved');
  expect(await page.evaluate(()=>app.serverSession.status)).toBe('completed');
  expect(readdirSync(new URL(`composites/${sid}/`,storage))).toHaveLength(1);
  expect(log.externalWrites).toEqual([]);
  expect(log.missing).toEqual([]);
  await page.screenshot({path:evidence+'phase2-saved-result.png'});
});

test('failed retake and delete keep old slot until backend acknowledges retry',async({page})=>{
  await setup(page);
  await page.evaluate(()=>{app.fullAutoMode=false;app.goToScreen('capture');});
  const photo=await fixture(page);
  await page.locator('input[multiple]').setInputFiles(Array.from({length:6},(_,i)=>({...photo,name:`retake-${i}.png`})));
  await expect(page.locator('#goToResultBtn')).toBeEnabled();
  const old=await page.evaluate(()=>app.photos[1].toDataURL());
  let fail=true;
  await page.route('**/api/sessions/*/photos',async route=> fail
    ? route.fulfill({status:503,contentType:'application/json',body:'{"error":{"message":"Retake chưa lưu (test)"}}'})
    : route.fallback());
  await page.evaluate(()=>{app.singleRetakeIndex=1;});
  await page.locator('#manualInstantSnapBtn').click();
  await expect(page.locator('#sessionSaveStatus')).toHaveAttribute('data-state','error');
  expect(await page.evaluate(()=>app.photos[1].toDataURL())).toBe(old);
  expect(await page.evaluate(()=>!!app.pendingPhotos[1])).toBe(true);
  fail=false;
  await page.locator('#retrySessionSaveBtn').click();
  await expect.poll(()=>page.evaluate(()=>app.serverSession.photos[1].revision)).toBe(2);
  expect(await page.evaluate(()=>app.photos[1].toDataURL())).not.toBe(old);
  let failDelete=true;
  await page.route('**/api/sessions/*/photos/1',async route=>failDelete
    ? route.fulfill({status:503,contentType:'application/json',body:'{"error":{"message":"Delete chưa lưu (test)"}}'})
    : route.fallback());
  await page.evaluate(()=>app.deleteSingleSlot(1));
  expect(await page.evaluate(()=>!!app.photos[1])).toBe(true);
  failDelete=false;
  await page.locator('#retrySessionSaveBtn').click();
  await expect.poll(()=>page.evaluate(()=>app.photos[1])).toBe(null);
  expect(await page.evaluate(()=>app.serverSession.photos.length)).toBe(5);
});

test('four-shot landscape mock session captures, retakes, composites and persists',async({page})=>{
  const log=await setup(page);
  await page.locator('#frameCardLandscape4').click();
  expect(await page.evaluate(()=>app.slotCount)).toBe(4);
  await page.evaluate(async()=>{app.fullAutoMode=false;await app.prepareSession();app.goToScreen('capture');});
  for(let i=0;i<4;i++) {
    await page.locator('#manualInstantSnapBtn').click();
    await expect.poll(()=>page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(i+1);
  }
  await expect(page.locator('#capturedCountBadge')).toHaveText('4 / 4 hoàn tất');
  await page.evaluate(()=>{app.singleRetakeIndex=2;});
  await page.locator('#manualInstantSnapBtn').click();
  await expect.poll(()=>page.evaluate(()=>app.serverSession.photos[2].revision)).toBe(2);
  await page.locator('#goToResultBtn').click();
  expect(await page.locator('#compositeCanvas').evaluate(c=>[c.width,c.height])).toEqual([1800,1200]);
  expect(await page.evaluate(()=>app.getSixSlotCoordinates(1800,1200).length)).toBe(4);
  await page.locator('#confirmSessionBtn').click();
  await expect(page.locator('#sessionSaveStatus')).toHaveAttribute('data-state','saved');
  expect(await page.evaluate(()=>app.serverSession.slot_count)).toBe(4);
  expect(await page.evaluate(()=>app.sessionPhase)).toBe('READY');
  expect(log).toEqual({errors:[],externalWrites:[],missing:[]});
});

async function confirmGuest(page,title) {
  await setup(page);
  await page.evaluate(()=>{app.fullAutoMode=false;app.goToScreen('capture');});
  const photo=await fixture(page);
  await page.locator('input[multiple]').setInputFiles(Array.from({length:6},(_,i)=>({...photo,name:`guest-${i}.png`})));
  await expect(page.locator('#goToResultBtn')).toBeEnabled();
  await page.locator('#goToResultBtn').click();
  await page.evaluate(title=>{app.customTexts.cardTitle=title;app.renderCompositeCanvas();},title);
  await page.locator('#confirmQRCodeBtn').click();
  await expect(page.locator('#qrStatusBadge')).toContainText('QR sẵn sàng');
  return page.evaluate(()=>({share:app.activeShare,session:app.serverSession}));
}

async function proxyPublicGuest(page) {
  // Exercise the real guest router at a synthetic HTTPS origin. This does not
  // prove Internet/DNS/TLS/phone reachability of a deployed public hostname.
  await page.route('https://photos.amazingrace.test/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    const response=await route.fetch({url:`${localUrl(8001)}${path}`});
    return route.fulfill({response});
  });
}

for(const count of [4,6])test(`Phase 5 host mock ${count} shots: live preview, fullscreen countdown, original capture, retake, QR and print`,async({page})=>{
  await page.setViewportSize({width:1180,height:820});
  await setup(page);
  await page.evaluate(count=>{
    app.fullAutoMode=false;app.countdownSeconds=1;
    if(count===4)app.selectPresetLayout('landscape_4');
    app.captureFrameIntoSlot=()=>{throw new Error('Host capture must never call browser screenshot fallback');};
    const draw=CanvasRenderingContext2D.prototype.drawImage;
    CanvasRenderingContext2D.prototype.drawImage=function(source,...args){
      if(['liveVideo','simLiveCanvas','hostCameraPreview'].includes(source?.id))throw new Error('Host capture must not draw preview into a shot');
      return draw.call(this,source,...args);
    };
  },count);
  let uploads=0;const commands=[];
  page.on('request',r=>{if(r.method()==='POST'&&/\/photos$/.test(r.url()))uploads++;if(r.method()==='POST'&&/\/camera\/captures$/.test(r.url()))commands.push({body:r.postDataJSON(),key:r.headers()['idempotency-key']});});
  await page.locator('#homeCameraSelect').selectOption('host_camera');
  await page.waitForFunction(()=>app.hostPreviewHealthy);
  await page.evaluate(()=>app.goToScreen('capture'));
  await expect(page.locator('#hostCameraPreview')).toBeVisible();
  await page.locator('#mainCaptureBtn').click();
  await expect(page.locator('body')).toHaveClass(/host-capture-fullscreen/);
  await expect(page.locator('#hostShotProgress')).toContainText(`1 / ${count}`);
  await page.screenshot({path:evidence+`phase5-capture-${count}.png`});
  await expect.poll(()=>page.evaluate(()=>app.photos.filter(Boolean).length),{timeout:45000}).toBe(count);
  await expect.poll(()=>page.evaluate(()=>app.isCapturingSequence)).toBe(false);
  expect(uploads).toBe(0);expect(commands).toHaveLength(count);
  expect(commands.map(c=>c.body)).toEqual(Array.from({length:count},(_,i)=>({slot_index:i})));
  const before=await page.evaluate(()=>app.serverSession.photos.map(p=>p.id));
  await page.evaluate(()=>app.triggerSingleRetake(1));
  await expect.poll(()=>page.evaluate(()=>app.serverSession.photos[1].id)).not.toBe(before[1]);
  const after=await page.evaluate(()=>app.serverSession.photos.map(p=>p.id));
  expect(after.filter((_,i)=>i!==1)).toEqual(before.filter((_,i)=>i!==1));
  expect(commands).toHaveLength(count+1);
  await page.locator('#goToResultBtn').click();
  await expect(page.locator('body')).not.toHaveClass(/host-capture-fullscreen/);
  await page.evaluate(()=>{app.selectedFilter='vivid';app.renderCompositeCanvas();});
  await page.locator('#confirmQRCodeBtn').click();
  await expect(page.locator('#qrStatusBadge')).toContainText('QR sẵn sàng');
  await page.locator('#printPhotoBtn').click();
  await expect(page.locator('#printStatus')).toContainText('Mock đã nhận');
  expect(await page.evaluate(()=>app.hostPreviewHealthy)).toBe(false);
});

test('Phase 5 built host mode uses the laptop API without iPad webcam permissions',async({page})=>{
  await page.addInitScript(()=>{
    window.webcamRequests=0;
    Object.defineProperty(crypto,'randomUUID',{value:undefined,configurable:true});
    Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>{window.webcamRequests++;throw new Error('Must not open the iPad camera');},enumerateDevices:async()=>[]}});
  });
  await page.route('https://fonts.googleapis.com/**',r=>r.fulfill({contentType:'text/css',body:''}));
  await page.goto(localUrl(4373));
  await page.waitForFunction(()=>app.cameraSource==='host'&&app.hostPreviewHealthy);
  expect(await page.evaluate(()=>window.webcamRequests)).toBe(0);
  await page.evaluate(()=>app.selectPresetLayout('landscape_4'));
  await page.evaluate(()=>{app.fullAutoMode=false;app.goToScreen('capture');});
  await page.locator('#manualInstantSnapBtn').click();
  await expect.poll(()=>page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(1);
  expect(await page.evaluate(()=>app.serverSession.layout)).toBe('landscape_4');
  expect(await page.evaluate(()=>app.serverSession.slot_count)).toBe(4);
  expect(await page.evaluate(()=>window.webcamRequests)).toBe(0);
  await page.evaluate(()=>app.goToScreen('home'));
});

test('Phase 5 leaving during a delayed connect releases the old camera and reconnects cleanly',async({page})=>{
  await setup(page);await page.locator('#homeCameraSelect').selectOption('host_camera');
  await page.waitForFunction(()=>app.hostPreviewHealthy);
  let release,hold=true;
  await page.route('**/camera/connect',async route=>{
    if(!hold)return route.fallback();hold=false;
    const response=await route.fetch();await new Promise(resolve=>{release=resolve;});
    await route.fulfill({response});
  });
  const pending=page.evaluate(()=>app.prepareHostCamera().then(()=>'',error=>error.message));
  await expect.poll(()=>typeof release).toBe('function');
  await page.evaluate(()=>app.goToScreen('home'));release();
  expect(await pending).toContain('hủy kết nối');
  expect(await page.evaluate(()=>app.hostPreviewHealthy)).toBe(false);
  expect(await page.evaluate(()=>app.hostConnectRequest)).toBe(null);
  await page.evaluate(()=>app.prepareHostCamera());
  await page.waitForFunction(()=>app.hostPreviewHealthy);
  await page.evaluate(()=>app.goToScreen('home'));
});

test('Phase 5 lost capture ACK, retry without another shot, stale preview recovery and countdown cancellation',async({page,context})=>{
  await setup(page);await page.locator('#homeCameraSelect').selectOption('host_camera');
  await page.waitForFunction(()=>app.hostPreviewHealthy);
  await page.evaluate(()=>{app.fullAutoMode=false;app.goToScreen('capture');});
  let requests=0,lose=true;
  await page.route('**/camera/captures',async route=>{
    requests++;if(lose){lose=false;await route.fetch();return route.abort('failed');}return route.fallback();
  });
  await page.locator('#manualInstantSnapBtn').click();
  await expect(page.locator('#retrySessionSaveBtn')).toBeVisible();
  const operation=await page.evaluate(()=>app.hostCaptureOperation.key);
  expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(0);
  await page.locator('#retrySessionSaveBtn').click();
  await expect.poll(()=>page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(1);
  const session=await page.evaluate(()=>app.serverSession);
  expect(session.shots_revision).toBe(1);expect(requests).toBe(2);
  expect(await page.evaluate(()=>app.hostCaptureOperation)).toBe(null);
  await page.evaluate(()=>{app.countdownSeconds=3;app.startOrContinueSequence();});
  await expect(page.locator('body')).toHaveClass(/host-capture-fullscreen/);
  await page.locator('#hostCaptureExit').click();await page.waitForTimeout(3300);
  expect(requests).toBe(2);
  const backend=localUrl(8001);
  const logged=await context.request.post(backend+'/api/admin/login',{headers:{'X-OSA-Login':'1'},data:{username:'test-host',password:process.env.OSA_TEST_ADMIN_PASSWORD}});
  expect(logged.ok()).toBe(true);const csrf=(await logged.json()).csrf_token;
  await context.request.post(backend+'/api/admin/camera/mock-failure',{headers:{'X-CSRF-Token':csrf},data:{failure:'stale_preview'}});
  await expect(page.locator('#hostCameraStatus')).toHaveAttribute('data-state','error');
  expect(await page.evaluate(()=>app.hostPreviewHealthy)).toBe(false);
  await expect(page.locator('#hostCameraPreview')).toBeHidden();
  await context.request.post(backend+'/api/admin/camera/mock-failure',{headers:{'X-CSRF-Token':csrf},data:{failure:null}});
  await page.getByRole('button',{name:'Kết nối lại camera',exact:true}).click();
  await page.waitForFunction(()=>app.hostPreviewHealthy);
  expect(await page.evaluate(()=>app.serverSession.photos[0].id)).toBe(session.photos[0].id);
  for(const failure of ['transfer','timeout']){
    await context.request.post(backend+'/api/admin/camera/mock-failure',{headers:{'X-CSRF-Token':csrf},data:{failure}});
    const count=await page.evaluate(()=>app.photos.filter(Boolean).length);
    await page.locator('#manualInstantSnapBtn').click();
    await expect(page.locator('#retrySessionSaveBtn')).toBeVisible();
    expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(count);
    await page.locator('#retrySessionSaveBtn').click();
    await expect.poll(()=>page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(count+1);
  }
  expect(operation).toBeTruthy();
  await page.evaluate(()=>app.goToScreen('home'));
});

test('Phase 4 kiosk print-ready, lost response deduplication, Host gallery/reprint/logout and guest isolation',async({page,context,browser})=>{
  const state=await confirmGuest(page,'Phase 4 print fixture');
  await expect(page.locator('#printPhotoBtn')).toBeEnabled();
  await page.locator('#printReadyBox summary').click();
  await expect(page.locator('#printReadyPreview')).toBeVisible();
  expect(await page.locator('#printReadyPreview').evaluate(img=>img.naturalHeight>img.naturalWidth)).toBe(true);
  await page.locator('#printCopies').selectOption('2');
  let lose=true;
  await page.route('**/api/sessions/*/print-jobs',async route=>{
    if(route.request().method()==='POST'&&lose){lose=false;await route.fetch();return route.abort('failed');}
    return route.fallback();
  });
  await page.locator('#printPhotoBtn').click();
  await expect(page.locator('#printStatus')).toContainText('Không kết nối');
  await expect(page.locator('#printCopies')).toBeDisabled();
  const originalKey=await page.evaluate(()=>app.printOperation.key);
  await page.locator('#printPhotoBtn').click();
  await expect(page.locator('#printStatus')).toContainText('Mock đã nhận');
  const job=await page.evaluate(()=>app.printOperation.job);
  expect(await page.evaluate(()=>app.printOperation.key)).toBe(originalKey);
  expect(job.copies).toBe(2);expect(job.physical_print_confirmed).toBe(false);
  expect(await page.evaluate(()=>window.printCalls)).toBe(0);
  await expect(page.locator('#printPhotoBtn')).toBeDisabled();
  await page.screenshot({path:evidence+'phase4-print-result.png'});
  const host=await context.newPage();
  await host.goto(localUrl(5173)+'/admin');
  await expect(host.locator('#login')).toBeVisible();
  await host.locator('input[name="username"]').fill('test-host');
  await host.locator('input[name="password"]').fill(process.env.OSA_TEST_ADMIN_PASSWORD);
  await host.getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await expect(host.locator('#dashboard')).toBeVisible();
  await expect(host.locator('#system')).toContainText('Backend online');
  await expect(host.locator('#jobs')).toContainText(job.id);
  await expect(host.locator('#jobs')).toContainText('2 bản');
  const card=host.locator('#gallery article').filter({has:host.locator(`img[src*="${state.session.session_id}"]`)});
  await card.getByRole('button').click();
  await expect(host.locator('#sessionInfo')).toContainText(state.session.session_id);
  await expect(host.locator('#composites img')).toHaveCount(2);
  await host.locator('#composites input').fill('1');
  await host.getByRole('button',{name:'In lại',exact:true}).click();
  await expect(host.locator('#message')).toContainText('Đã tạo job');
  const listed=await host.evaluate(async()=>{const r=await fetch('/api/admin/print-jobs');return r.json();});
  const ownJobs=listed.items.filter(j=>j.final_id===state.share.final_id);
  expect(ownJobs).toHaveLength(2);expect(ownJobs.map(j=>j.copies).sort()).toEqual([1,2]);
  expect(ownJobs.every(j=>!j.physical_print_confirmed)).toBe(true);
  const downloadEvent=host.waitForEvent('download');
  await host.getByRole('link',{name:'Tải bản in có QR'}).click();
  const {createHash}=await import('node:crypto');
  expect(createHash('sha256').update(readFileSync(await (await downloadEvent).path())).digest('hex')).toBe(state.share.print_ready.sha256);
  await host.screenshot({path:evidence+'phase4-host-dashboard.png'});
  const guestContext=await browser.newContext();
  const guest=await guestContext.newPage();
  expect((await guest.request.get(localUrl(8001)+'/api/admin/sessions')).status()).toBe(401);
  expect((await guest.request.post(localUrl(8001)+'/api/admin/print-jobs',{data:{session_id:state.session.session_id,final_id:state.share.final_id,copies:1},headers:{'Idempotency-Key':crypto.randomUUID()}})).status()).toBe(401);
  await proxyPublicGuest(guest);await guest.goto(state.share.share_url);
  await expect(guest.locator('#guestPhoto')).toBeVisible();
  expect(await guest.locator('img').count()).toBe(1);
  await host.locator('#logout').click();await expect(host.locator('#login')).toBeVisible();
  expect(await host.evaluate(async()=>(await fetch('/api/admin/sessions')).status)).toBe(401);
  await guestContext.close();
});

test('guest A/B pages display and download only their own confirmed photo',async({page,context})=>{
  const a=await confirmGuest(page,'Guest A fixture');
  const ownerB=await context.newPage();
  const b=await confirmGuest(ownerB,'Guest B fixture');
  expect(a.share.share_url).not.toBe(b.share.share_url);
  const guest=await context.newPage();
  await guest.setViewportSize({width:390,height:844});
  await proxyPublicGuest(guest);
  for(const state of [a,b]) {
    await guest.goto(state.share.share_url);
    await expect(guest.locator('#guestPhoto')).toBeVisible();
    expect(await guest.locator('img').count()).toBe(1);
    expect(await guest.locator('a').count()).toBe(1);
    expect(await guest.locator('body').innerText()).not.toContain('Gallery');
    expect(await guest.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    const event=guest.waitForEvent('download');
    await guest.locator('#guestDownload').click();
    const download=await event;
    const {createHash}=await import('node:crypto');
    expect(createHash('sha256').update(readFileSync(await download.path())).digest('hex')).toBe(state.share.print_ready.sha256);
  }
  await guest.screenshot({path:evidence+'phase3-guest-mobile.png'});
  await guest.goto('https://photos.amazingrace.test/p/'+('z'.repeat(43)));
  await expect(guest.getByRole('alert')).toBeVisible();
  expect(await guest.locator('img').count()).toBe(0);
  expect(await guest.locator('a').count()).toBe(0);
});

test('confirmed session keeps one composite and stable QR; editing and retake require a new guest',async({page,context})=>{
  let finalizes=0, composites=0;
  page.on('request',request=>{
    if(request.url().endsWith('/finalize')) finalizes++;
    if(request.url().endsWith('/composite')&&request.method()==='PUT') composites++;
  });
  const original=await confirmGuest(page,'Stable QR fixture');
  expect(finalizes).toBe(1);
  expect(composites).toBe(1);
  await page.evaluate(()=>{for(let i=0;i<5;i++)app.renderCompositeCanvas();});
  await expect(page.locator('#tabPanel_filters')).toHaveAttribute('inert','');
  await expect(page.locator('[id^="stepNav"]')).toHaveCount(0);
  expect(finalizes).toBe(1);
  expect(composites).toBe(1);
  await expect(page.locator('#qrStatusBadge')).toContainText('QR sẵn sàng');
  expect(await page.locator('#qrExternalUrlInput').inputValue()).toBe(original.share.share_url);
  await page.locator('#confirmSessionBtn').click();
  expect(finalizes).toBe(1);
  await expect(page.locator('#qrStatusBadge')).toContainText('QR sẵn sàng');
  expect(await page.locator('#qrExternalUrlInput').inputValue()).toBe(original.share.share_url);
  expect(composites).toBe(1);
  const oldGuest=await context.newPage();
  await proxyPublicGuest(oldGuest);
  await oldGuest.goto(original.share.share_url);
  await expect(oldGuest.locator('#guestPhoto')).toBeVisible();
  expect(original.share.share_url).not.toContain('localhost');
});

test('known failed final confirmation preserves working photos and allows retake before a successful retry',async({page})=>{
  await setup(page);await page.evaluate(()=>{app.fullAutoMode=false;app.goToScreen('capture');});
  const photo=await fixture(page);
  await page.locator('input[multiple]').setInputFiles(Array.from({length:6},(_,i)=>({...photo,name:`recover-${i}.png`})));
  await expect(page.locator('#goToResultBtn')).toBeEnabled();await page.locator('#goToResultBtn').click();
  let fail=true;
  await page.route('**/api/sessions/*/complete',route=>fail?route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{message:'Không commit được composite (test)'}})}):route.fallback());
  await page.locator('#confirmSessionBtn').click();
  await expect(page.locator('#sessionSaveStatus')).toHaveAttribute('data-state','error');
  expect(await page.evaluate(()=>app.photos.every(Boolean))).toBe(true);
  await expect(page.locator('#tabPanel_filters')).not.toHaveAttribute('inert','');
  const sid=await page.evaluate(()=>app.sessionContext.id);
  const storage=new URL('../../../.tools/e2e-backend/',import.meta.url);
  expect(readdirSync(new URL(`originals/${sid}/`,storage))).toHaveLength(6);
  await page.evaluate(()=>{app.goToScreen('capture');app.singleRetakeIndex=0;});
  await page.locator('#manualInstantSnapBtn').click();
  await expect.poll(()=>page.evaluate(()=>app.serverSession.photos[0].revision)).toBe(2);
  fail=false;await page.locator('#goToResultBtn').click();await page.locator('#confirmSessionBtn').click();
  await expect(page.locator('#qrStatusBadge')).toContainText('QR sẵn sàng');
  expect(readdirSync(new URL(`originals/${sid}/`,storage))).toHaveLength(0);
  expect(readdirSync(new URL(`composites/${sid}/`,storage))).toHaveLength(1);
  expect(await page.evaluate(()=>app.photos.every(p=>p===null))).toBe(true);
});

test('lost finalize response keeps saved photo, QR retries reuse the same final/token',async({page})=>{
  await setup(page);
  let loseResponse=true;
  await page.route('**/api/sessions/*/finalize',async route=>{
    const response=await route.fetch();
    if(loseResponse) {
      loseResponse=false;
      return route.fulfill({status:503,contentType:'application/json',body:'{"error":{"message":"Mất phản hồi QR (test)"}}'});
    }
    return route.fulfill({response});
  });
  await page.evaluate(()=>{app.fullAutoMode=false;app.goToScreen('capture');});
  const photo=await fixture(page);
  await page.locator('input[multiple]').setInputFiles(Array.from({length:6},(_,i)=>({...photo,name:`qr-${i}.png`})));
  await expect(page.locator('#goToResultBtn')).toBeEnabled();
  await page.locator('#goToResultBtn').click();
  await page.locator('#confirmSessionBtn').click();
  await expect(page.locator('#sessionSaveStatus')).toHaveAttribute('data-state','saved');
  await expect(page.locator('#qrDescriptionText')).toContainText('Mất phản hồi QR');
  await expect(page.locator('#qrExternalOpenBtn')).not.toHaveAttribute('href');
  const sid=await page.evaluate(()=>app.sessionContext.id);
  const qrDir=new URL(`../../../.tools/e2e-backend/qrcodes/${sid}/`,import.meta.url);
  expect(readdirSync(qrDir)).toHaveLength(1);
  await page.evaluate(()=>app.generateQRCodeForCurrentPhoto(true));
  await expect(page.locator('#qrStatusBadge')).toContainText('QR sẵn sàng');
  expect(readdirSync(qrDir)).toHaveLength(1);
});

test('guest Start refuses unavailable host camera, then recovers into automatic review without finalizing',async({page})=>{
  await setup(page);
  let captures=0;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/camera/captures'))captures++;});
  await page.evaluate(()=>{app.selectPresetLayout('landscape_4');app.countdownSeconds=1;app.fullAutoMode=false;});
  await page.route('**/camera/connect',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{message:'Camera chưa sẵn sàng: kiểm tra kết nối USB.'}})}));
  await page.locator('#homeCameraSelect').selectOption('host_camera');
  await page.locator('#setupStartCaptureBtn').click();
  await expect(page.locator('#setupCameraStatus')).toContainText('Camera chưa sẵn sàng');
  await expect(page.locator('#screenHome')).toBeVisible();
  await expect(page.locator('body')).not.toHaveClass(/host-capture-fullscreen/);
  expect(captures).toBe(0);
  expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(0);
  await page.unroute('**/camera/connect');
  await page.locator('#setupStartCaptureBtn').click();
  await expect(page.locator('body')).toHaveClass(/host-capture-fullscreen/);
  await expect(page.locator('#screenResult')).toBeVisible({timeout:30000});
  await expect(page.locator('body')).toHaveAttribute('data-workflow','review');
  await expect(page.locator('#guestDeliveryPanel')).toBeHidden();
  expect(captures).toBe(4);
  expect(await page.evaluate(()=>app.serverSession.composite)).toBe(null);
  expect(await page.evaluate(()=>app.serverSession.finalized)).toBe(false);
});

test('guest page shows loading and network error, then recovers after reload',async({page,context})=>{
  const owner=await confirmGuest(page,'Loading fixture');
  const guest=await context.newPage();
  await proxyPublicGuest(guest);
  let release;
  const gate=new Promise(resolve=>{release=resolve;});
  const imagePattern='https://photos.amazingrace.test/p/*/image';
  await guest.route(imagePattern,async route=>{await gate;await route.abort('failed');});
  await guest.goto(owner.share.share_url,{waitUntil:'domcontentloaded'});
  await expect(guest.locator('#loading')).toBeVisible();
  await expect(guest.locator('#guestDownload')).toBeHidden();
  release();
  await expect(guest.locator('#error')).toBeVisible();
  await expect(guest.locator('#loading')).toBeHidden();
  await expect(guest.locator('#guestDownload')).toBeHidden();
  await guest.unroute(imagePattern);
  await guest.reload();
  await expect(guest.locator('#guestPhoto')).toBeVisible();
  await expect(guest.locator('#guestDownload')).toBeVisible();
});
