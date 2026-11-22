import {test,expect,request} from '@playwright/test';
let cookies;
test.use({actionTimeout:10000});
test.beforeAll(async()=>{
  const api=await request.newContext({baseURL:'http://127.0.0.1:5188'});
  const response=await api.post('/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:'preview-only-disposable-pairing-key'}});
  expect(response.ok()).toBe(true);cookies=(await api.storageState()).cookies;await api.dispose();
});

async function holdCaptureUntilValidation(page){
  const state={current:null};
  await page.route('**/camera/captures',async route=>{
    const shot={key:route.request().headers()['idempotency-key'],ack:false,checks:0,fail:false};
    const validated=new Promise(resolve=>{shot.release=resolve;});
    state.current=shot;
    await validated;
    if(shot.fail)return route.fulfill({status:504,json:{error:{code:'timeout',stage:'transfer',uncertain:true,message:'Test JPEG transfer timeout'}}});
    await route.fallback();
  });
  await page.route('**/camera/status',route=>{
    const shot=state.current;
    if(!shot||shot.key!==route.request().headers()['idempotency-key'])return route.fallback();
    shot.checks++;
    return route.fulfill({json:{
      capture_progress:{capture_id:shot.key,stage:shot.ack?'receiving_original':'shutter',shutter_acknowledged:shot.ack},
      camera_progress:{capture_id:shot.key,stage:'jpeg_transfer'},
    }});
  });
  return state;
}

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
  await expect(page.locator('#mainCaptureBtnText')).toHaveText('Pause');
  await page.locator('#mainCaptureBtn').click();
  await expect(page.locator('#countdownOverlay')).toBeHidden();
  const transitions=await holdCaptureUntilValidation(page);
  const shutter=page.locator('#captureShutter');
  const openPositions=await shutter.evaluate(element=>['::before','::after'].map(side=>{
    const matrix=new DOMMatrixReadOnly(getComputedStyle(element,side).transform);
    return [matrix.m41,matrix.m42];
  }));
  expect(openPositions[0][0]).toBeLessThan(0);expect(openPositions[1][0]).toBeGreaterThan(0);
  expect(openPositions.map(pos=>pos[1])).toEqual([0,0]);
  for(let index=0;index<count;index++){
    await expect(page.locator('#completeCaptureBtn')).toBeHidden();
    const previous=transitions.current;
    await page.locator('#manualInstantSnapBtn').click();
    await expect.poll(()=>transitions.current!==previous&&transitions.current?.checks>0).toBe(true);
    const shot=transitions.current;
    try{
      await expect(shutter).toBeHidden();
      shot.ack=true;
      await expect(shutter).toHaveClass('is-closed');
      await expect(shutter).toBeVisible();
      if(!index){
        const coverage=await shutter.evaluate(element=>{
          const rect=element.getBoundingClientRect(),art=getComputedStyle(element,'::before');
          const safeTop=document.getElementById('boothHeader').getBoundingClientRect().bottom;
          return {fillsBelowLogos:rect.x===0&&rect.y>=safeTop-1&&rect.width===innerWidth&&Math.abs(rect.bottom-innerHeight)<1,
            approvedArtwork:art.backgroundImage.includes('Theme-ptb-final'),size:art.backgroundSize};
        });
        expect(coverage).toEqual({fillsBelowLogos:true,approvedArtwork:true,size:'100% auto'});
        await expect(shutter).toHaveCSS('visibility','visible');
        const closedAt=await shutter.evaluate(async element=>{
          await Promise.allSettled(element.getAnimations({subtree:true}).map(animation=>animation.finished));
          return performance.now();
        });
        const previousFrame=await page.evaluate(()=>app.hostFrameSequence);
        shot.release();
        await expect.poll(()=>page.evaluate(()=>app.hostFrameSequence)).toBeGreaterThan(previousFrame);
        await expect(shutter).toHaveClass('is-closed');
        await page.waitForFunction(()=>!document.getElementById('captureShutter').classList.contains('is-closed'));
        expect(await page.evaluate(closedAt=>performance.now()-closedAt,closedAt)).toBeGreaterThanOrEqual(3950);
      }
    }finally{shot.release();}
    await expect(page.locator('#capturedCountBadge')).toHaveText(`${index+1} / ${count} complete`);
    await expect(shutter).toBeHidden();
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

test('a JPEG timeout opens the shutter overlay and leaves the failed slot empty',async({page,context})=>{
  await context.addCookies(cookies);
  await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  await page.locator('#setupStartCaptureBtn').click();
  await page.locator('#mainCaptureBtn').click();
  const transitions=await holdCaptureUntilValidation(page);
  await page.locator('#manualInstantSnapBtn').click();
  await expect.poll(()=>transitions.current?.checks||0).toBeGreaterThan(0);
  const shot=transitions.current,shutter=page.locator('#captureShutter');
  try{
    shot.ack=true;
    await expect(shutter).toHaveClass('is-closed');
    shot.fail=true;
  }finally{shot.release();}
  await expect(shutter).toBeHidden();
  await expect(page.locator('#retrySessionSaveBtn')).toBeVisible();
  await expect(page.locator('#capturedCountBadge')).toHaveText('0 / 6 complete');
  await expect(page.locator('#screenCapture')).toBeVisible();
});

test('slow validation keeps the curtain closed past the minimum hold',async({page,context})=>{
  await context.addCookies(cookies);
  await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  await page.locator('#setupStartCaptureBtn').click();
  await page.locator('#mainCaptureBtn').click();
  const transitions=await holdCaptureUntilValidation(page);
  await page.locator('#manualInstantSnapBtn').click();
  await expect.poll(()=>transitions.current?.checks||0).toBeGreaterThan(0);
  const shot=transitions.current,shutter=page.locator('#captureShutter');
  try{
    shot.ack=true;
    await expect(shutter).toHaveClass('is-closed');
    await page.waitForTimeout(4550);
    await expect(shutter).toHaveClass('is-closed');
    await expect(page.locator('#capturedCountBadge')).toHaveText('0 / 6 complete');
  }finally{shot.release();}
  await expect(shutter).toBeHidden();
  await expect(page.locator('#capturedCountBadge')).toHaveText('1 / 6 complete');
});

async function expectFullscreenPreview(page){
  const preview=page.locator('#cameraPreviewPanel');
  await expect(preview).toBeVisible();
  expect(await preview.evaluate(panel=>{
    const {x,y,width,height}=panel.getBoundingClientRect();
    return [x,y,width-innerWidth,height-innerHeight];
  })).toEqual([0,0,0,0]);
  await expect(page.locator('#hostCameraPreview')).toHaveCSS('object-fit','contain');
  expect(await preview.evaluate(panel=>{
    const box=id=>document.getElementById(id).getBoundingClientRect();
    const {width,height,left,right,top}=panel.querySelector('.capture-preview-feed').getBoundingClientRect();
    const progress=box('hostShotProgress'), countdown=box('countdownOverlay');
    const reads=[document.getElementById('hostShotProgress'),document.getElementById('countdownNumber')];
    return height===innerHeight&&top===0&&Math.abs(left-(innerWidth-right))<1
      &&Math.abs(progress.width-countdown.width)<1&&width>innerWidth*.7
      &&progress.right<=left&&countdown.left>=right&&progress.top===countdown.top
      &&reads.every(el=>el.scrollWidth<=el.clientWidth);
  })).toBe(true);
  await expect(page.locator('#countdownLabel')).toHaveCount(0);
  for(const selector of ['#boothHeader','#setupOptions','#sixSlotsGrid','#manualInstantSnapBtn','.capture-preview-guide']){
    await expect(page.locator(selector)).toBeHidden();
  }
}

test('fullscreen countdown restores Booth after Escape and automatic JPEG failure',async({page,context})=>{
  await context.addCookies(cookies);
  await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  await page.locator('#timerBtn10').click();await page.locator('#setupStartCaptureBtn').click();
  await expect(page.locator('#countdownNumber')).toHaveText('10');
  await expectFullscreenPreview(page);
  await page.setViewportSize({width:390,height:844});
  await expectFullscreenPreview(page);
  await page.setViewportSize({width:1920,height:1080});
  await expectFullscreenPreview(page);
  await page.keyboard.press('Escape');
  await expect(page.locator('#boothHeader')).toBeVisible();
  await expect(page.locator('#countdownOverlay')).toBeHidden();
  await expect(page.locator('#manualInstantSnapBtn')).toBeVisible();
  expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(0);

  const transitions=await holdCaptureUntilValidation(page);
  await page.locator('#mainCaptureBtn').click();
  await expect.poll(()=>transitions.current?.checks||0,{timeout:20000}).toBeGreaterThan(0);
  const shot=transitions.current,shutter=page.locator('#captureShutter');
  try{
    shot.ack=true;
    await expect(shutter).toHaveClass('is-closed');
    expect(await shutter.boundingBox()).toEqual({x:0,y:0,width:1920,height:1080});
    await page.waitForTimeout(4550);
    await expect(shutter).toHaveClass('is-closed');
    await expect(page.locator('#hostShotProgress')).toHaveText('0 / 6');
    shot.fail=true;
  }finally{shot.release();}
  await expect(shutter).toBeHidden();
  await expect(page.locator('#boothHeader')).toBeVisible();
  await expect(page.locator('#retrySessionSaveBtn')).toBeVisible();
  await expect(page.locator('#capturedCountBadge')).toHaveText('0 / 6 complete');
});

for(const count of [4,6])test(`compact pause control: ${count} photos and automatic review`,async({page,context})=>{
  await context.addCookies(cookies);await page.setViewportSize({width:1024,height:768});
  let finalizations=0;page.on('request',r=>{if(r.method()==='POST'&&/\/(complete|finalize)$/.test(r.url()))finalizations++;});
  await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  if(count===4){await page.locator('#frameCardLandscape4').click();await expect.poll(()=>page.evaluate(()=>app.persistenceBusy)).toBe(false);}
  await page.locator('#timerBtn3').click();await page.locator('#setupStartCaptureBtn').click();
  await expect(page.locator('#countdownNumber')).toBeVisible();
  await expectFullscreenPreview(page);
  await expect(page.locator('#hostShotProgress')).toHaveText(`0 / ${count}`);
  await expect(page.locator('#countdownNumber')).toHaveText('2');
  await page.locator('#mainCaptureBtn').click();await expect(page.locator('#mainCaptureBtnText')).toHaveText('Resume Capture');
  await expect(page.locator('body')).not.toHaveClass(/host-capture-fullscreen/);
  await expect(page.locator('#mainCaptureBtn')).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('#hostCaptureExit')).toHaveCount(0);
  await expect(page.locator('#capturedCountBadge')).toHaveText(`0 / ${count} complete`);
  await expect(page.locator('#manualInstantSnapBtn')).toBeVisible();await expect(page.locator('#resetAllShotsBtn')).toBeVisible();
  await expect(page.locator('#countdownOverlay')).toBeHidden();
  const remaining=await page.locator('#countdownNumber').textContent();await page.waitForTimeout(1300);
  await expect(page.locator('#countdownNumber')).toHaveText(remaining);expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(0);
  await page.locator('#mainCaptureBtn').click();await expect(page.locator('#mainCaptureBtnText')).toHaveText('Pause');
  await expect(page.locator('#hostShotProgress')).toHaveText(`1 / ${count}`,{timeout:18000});
  await expect(page.locator('#countdownNumber')).toBeVisible();
  await expectFullscreenPreview(page);
  await expect(page.locator('body')).toHaveAttribute('data-workflow','review',{timeout:70000});
  await expect(page.locator('body')).not.toHaveClass(/host-capture-fullscreen/);
  expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(count);
  expect(await page.evaluate(()=>app.serverSession.finalized)).toBe(false);expect(finalizations).toBe(0);
  expect(await page.evaluate(()=>app.serverSession.photos.map(photo=>photo.slot_index))).toEqual(Array.from({length:count},(_,i)=>i));
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
