import { test, expect } from '@playwright/test';
import { readFileSync, mkdirSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const evidence = fileURLToPath(new URL('../../../docs/screenshots/', import.meta.url));
mkdirSync(evidence,{recursive:true});
const distAssets = new URL('../../dist/assets/', import.meta.url);
const cssFile = readdirSync(distAssets).find(n=>n.endsWith('.css'));
const compiledCSS = readFileSync(new URL(cssFile, distAssets),'utf8');

async function setup(page, url='http://127.0.0.1:5173', expectMock=true) {
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
  if(url.includes(':5174')) {
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

test('Home/setup, timers, mock selector, mirror, modal/calibrator and delayed-start cancellation', async({page})=>{
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
  await page.evaluate(()=>app.openSettingsModal());
  await page.locator('#chkFullAuto').uncheck();
  await expect(page.locator('#chkAutoPrintPopup')).not.toBeChecked();
  await page.evaluate(()=>app.autoDetectTransparentHolesFromFrame());
  await expect(page.locator('#slotDetectStatus')).toContainText('Vui lòng');
  await page.screenshot({path:evidence+'modular-settings.png'});
  await page.evaluate(()=>app.closeSettingsModal());
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
  for(let i=0;i<6;i++){await page.clock.runFor(3000);await page.clock.fastForward(950);}
  await expect(page.locator('#capturedCountBadge')).toHaveText('6 / 6 hoàn tất');
  await page.screenshot({path:evidence+'modular-capture.png'});
  for(const slot of [1,4]) {
    await page.locator('#sixSlotsGrid > div').nth(slot).click();
    expect(await page.evaluate(()=>app.singleRetakeIndex)).toBe(slot);
    await page.clock.runFor(3000);
    expect(await page.evaluate(()=>app.singleRetakeIndex)).toBe(null);
  }
  await page.locator('#sixSlotsGrid > div').nth(1).locator('button').dispatchEvent('click');
  await expect(page.locator('#goToResultBtn')).toBeDisabled();
  expect(await page.evaluate(()=>app.isCapturingSequence)).toBe(false);
  await page.locator('#manualInstantSnapBtn').click();
  await page.locator('#goToResultBtn').click();
  await expect(page.locator('#screenResult')).toBeVisible();
  await expect(page.locator('#qrStatusBadge')).toContainText('DEMO');
  await expect(page.locator('#qrExternalOpenBtn')).not.toHaveAttribute('href');
  await page.evaluate(()=>{app.goToScreen('capture');app.resetSessionShots();app.fullAutoMode=true;});
  for(let i=0;i<6;i++) await page.locator('#manualInstantSnapBtn').click();
  await page.clock.runFor(4000);
  await expect(page.locator('#screenResult')).toBeVisible();
  expect(await page.evaluate(()=>window.printCalls)).toBe(0);
  await page.evaluate(()=>{app.fullAutoMode=false;app.startNewGuestSession();});
  await expect(page.locator('#screenHome')).toBeVisible();
  expect(await page.evaluate(()=>app.photos.every(p=>p===null)&&app.placedStickers.length===0)).toBe(true);
  expect(log).toEqual({errors:[],externalWrites:[],missing:[]});
});

test('uploads, six transparent regions, all filters/categories, stickers mouse/touch, text, download and print boundary',async({page})=>{
  const log=await setup(page);
  const photo=await fixture(page), frame=await fixture(page,true);
  await page.evaluate(()=>{app.fullAutoMode=false;app.goToScreen('capture');});
  await page.locator('input[multiple]').setInputFiles(Array.from({length:6},(_,i)=>({...photo,name:`fixture-${i}.png`})));
  await expect(page.locator('#goToResultBtn')).toBeEnabled();
  await page.locator('#goToResultBtn').click();
  await page.locator('#customFrameInputMain').setInputFiles(frame);
  await page.waitForFunction(()=>app.detectedSlots?.length===6);
  await page.evaluate(()=>app.openSlotCalibrator());
  await page.locator('#slotPadX').fill('0');
  expect(await page.evaluate(()=>app.slotMetrics.padX)).toBe(0);
  await page.evaluate(()=>{app.autoDetectTransparentHolesFromFrame();app.closeSettingsModal();});
  expect(await page.evaluate(()=>app.detectedSlots.length)).toBe(6);
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
  await page.locator('#inputTopText').fill('OSA TEST');
  await page.locator('#inputCardTitle').fill('Refactor test');
  await page.locator('#inputBrandingText').fill('Fixture only');
  expect(await page.evaluate(()=>app.customTexts.topText)).toBe('OSA TEST');
  await page.evaluate(()=>app.openMobilePreviewModal());
  await expect(page.locator('#mobileModalImage')).toHaveAttribute('src',/^data:image\/png/);
  await page.locator('#mobilePreviewModal button').last().click();
  const downloadEvent=page.waitForEvent('download');
  await page.getByText('TẢI ẢNH VỀ',{exact:true}).click();
  expect((await downloadEvent).suggestedFilename()).toMatch(/^osa-booth-.*\.png$/);
  await page.evaluate(()=>app.triggerPrint());
  await page.waitForFunction(()=>window.printCalls===1);
  await page.evaluate(()=>app.showToast('Regression fixture','info'));
  await expect(page.locator('#toastContainer')).toContainText('Regression fixture');
  await page.screenshot({path:evidence+'modular-result.png'});
  await page.evaluate(()=>app.clearAllStickers());
  expect(await page.evaluate(()=>app.placedStickers.length)).toBe(0);
  await page.waitForTimeout(100);
  expect(await page.evaluate(()=>window.printCalls)).toBe(1);
  expect(log).toEqual({errors:[],externalWrites:[],missing:[]});
});

test('baseline screenshots and pixel-identical compositor output for all filters and both presets',async({page,context})=>{
  const baseline=await context.newPage();
  await setup(baseline,'http://127.0.0.1:5174');
  await setup(page);
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
  await baseline.evaluate(()=>app.openSettingsModal());
  await baseline.screenshot({path:evidence+'legacy-settings.png'});
});

test('built artifact loads on iPad portrait/landscape with functional dynamic handlers',async({page})=>{
  const log=await setup(page,'http://127.0.0.1:4173');
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
  const log=await setup(page,'http://127.0.0.1:4273',false);
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
