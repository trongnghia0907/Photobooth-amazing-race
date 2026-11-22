import {test,expect,request} from '@playwright/test';
import {readFileSync} from 'node:fs';

let cookies;
test.beforeAll(async()=>{
  const api=await request.newContext({baseURL:'http://127.0.0.1:5188'});
  expect((await api.post('/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:'preview-only-disposable-pairing-key'}})).ok()).toBe(true);
  cookies=(await api.storageState()).cookies;await api.dispose();
});
test.beforeEach(async({context})=>context.addCookies(cookies));
test.afterEach(async({page})=>{await page.evaluate(async()=>{app.releaseHostCamera();await app.hostReleaseRequest;}).catch(()=>{});});

async function sonyCapabilities(page){
  await page.route('**/camera/connect',async route=>{
    const response=await route.fetch(),data=await response.json();
    // Physical capability contract only. No real Sony device is used here.
    data.capabilities={...data.capabilities,adapter:'sony_zve10',name:'TEST Sony transport',demo:false,physical_shutter:true,original_file:true,hardware_verified:false};
    await route.fulfill({response,json:data});
  });
}

test('development Sony contract tolerates first pending frame and does not reopen USB',async({page})=>{
  await sonyCapabilities(page);let connects=0,frames=0,inflight=0,maxInflight=0;
  page.on('request',r=>{if(r.url().endsWith('/camera/connect'))connects++;});
  await page.route('**/camera/frame',async route=>{
    inflight++;maxInflight=Math.max(maxInflight,inflight);
    try{
      if(++frames===1)return await route.fulfill({status:503,json:{error:{code:'not_ready',stage:'preview',message:'TEST Sony Live View warming up'}}});
      await route.fulfill({response:await route.fetch()});
    }finally{inflight--;}
  });
  await page.goto('/?previewStats=1');await page.waitForFunction(()=>window.app?.hostPreviewDiagnostics?.frames>=20);
  expect(connects).toBe(1);expect(maxInflight).toBe(1);
  await expect(page.locator('#demoModeBadge')).toHaveCount(0);
  await expect(page.locator('#hostCameraPreview')).toBeVisible();
  await expect(page.locator('#hostPreviewStats')).toContainText(/FPS.*request p95.*frame age/);
  await expect(page.locator('#hostPreviewStats')).toContainText(/next paint \d+.*timer late/);
  const metrics=await page.evaluate(()=>app.hostPreviewPerformance());
  expect(metrics.samples).toBeGreaterThanOrEqual(20);
  expect(metrics.displayedFPS).toBeGreaterThan(0);
  expect(metrics.responseMs.p95).toBeGreaterThanOrEqual(metrics.responseMs.p50);
  expect(metrics.paintAgeUpperBoundMs.p95).toBeGreaterThan(0);
  expect(metrics.pendingRender).toBeLessThanOrEqual(1);
  console.log('SIMULATED Sony capability / Mock transport preview:',JSON.stringify(metrics));
});

test('old sequence is ignored, temporary busy recovers, released preview cleans up',async({page})=>{
  await sonyCapabilities(page);await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  await expect(page.locator('#hostPreviewStats')).toBeHidden();
  const before=await page.evaluate(()=>app.hostFrameSequence);let stale=true,connects=0;
  page.on('request',r=>{if(r.url().endsWith('/camera/connect'))connects++;});
  await page.route('**/camera/frame',async route=>{
    const response=await route.fetch();
    if(stale)return route.fulfill({response,headers:{...response.headers(),'x-frame-sequence':String(before)}});
    await route.fulfill({response});
  });
  await page.waitForFunction(()=>app.hostPreviewDiagnostics.lastFailure==='preview_pending');
  expect(await page.evaluate(()=>app.hostPreviewPerformance().discardedStaleFrames)).toBeGreaterThan(0);
  expect(await page.evaluate(()=>app.hostFrameSequence)).toBe(before);
  stale=false;await page.waitForFunction(n=>app.hostFrameSequence>n,before);
  expect(connects).toBe(0);
  await page.evaluate(()=>app.releaseHostCamera());
  expect(await page.evaluate(()=>({timer:app.hostPreviewTimer,watchdog:app.hostPreviewWatchdog,url:app.hostFrameUrl,healthy:app.hostPreviewHealthy}))).toEqual({timer:null,watchdog:null,url:null,healthy:false});
});

if(process.env.PREVIEW_BASELINE_FILE)test('baseline preview pacing measurement (Mock transport only)',async({page})=>{
  const source=readFileSync(process.env.PREVIEW_BASELINE_FILE,'utf8');
  await page.route('**/src/services/host-camera.js*',route=>route.fulfill({contentType:'application/javascript',body:source}));
  await page.addInitScript(()=>{
    window.previewTimes=[];
    new MutationObserver(records=>{
      for(const r of records)if(r.target.id==='hostCameraPreview'&&r.attributeName==='src'&&r.target.hasAttribute('src'))window.previewTimes.push(performance.now());
    }).observe(document,{subtree:true,attributes:true,attributeFilter:['src']});
  });
  await page.goto('/');await page.waitForFunction(()=>window.previewTimes?.length>=20);
  const result=await page.evaluate(()=>{
    const times=window.previewTimes,intervals=times.slice(1).map((t,i)=>t-times[i]).sort((a,b)=>a-b);
    return {samples:times.length,fps:(times.length-1)*1000/(times.at(-1)-times[0]),intervalMs:{p50:intervals[Math.floor(intervals.length/2)],p95:intervals[Math.floor(intervals.length*.95)],max:intervals.at(-1)}};
  });
  console.log('BEFORE change / Mock transport preview:',JSON.stringify(result));
});
