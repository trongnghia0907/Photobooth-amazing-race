import {test,expect,request} from '@playwright/test';
let cookies;
test.beforeAll(async()=>{
  const client=await request.newContext({baseURL:'http://127.0.0.1:5188'});
  const paired=await client.post('/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:'preview-only-disposable-pairing-key'}});
  expect(paired.ok()).toBe(true);cookies=(await client.storageState()).cookies;await client.dispose();
});
test.afterEach(async({page})=>{await page.evaluate(async()=>{app.releaseHostCamera();await app.hostReleaseRequest;}).catch(()=>{});});

test('lost first frame and temporary preview disconnect retry reads without reconnecting camera',async({page,context})=>{
  await context.addCookies(cookies);
  let connects=0,fail=true;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/camera/connect'))connects++;});
  await page.route('**/camera/frame',route=>{if(fail){fail=false;return route.abort('connectionrefused');}return route.fallback();});
  await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  expect(connects).toBe(1);
  await page.evaluate(()=>app.capturePhoto(0));
  const before=await page.evaluate(()=>app.photos[0].toDataURL());
  let unavailable=true;
  await page.route('**/camera/frame',route=>unavailable?route.abort('connectionrefused'):route.fallback());
  await expect.poll(()=>page.evaluate(()=>app.hostPreviewHealthy)).toBe(false);
  await expect(page.locator('#hostCameraPreview')).toBeHidden();
  await page.locator('#timerBtn7').click();expect(await page.evaluate(()=>app.countdownSeconds)).toBe(7);
  unavailable=false;await page.waitForFunction(()=>app.hostPreviewHealthy);
  expect(connects).toBe(1);
  expect(await page.evaluate(()=>app.photos[0].toDataURL())).toBe(before);
  expect(await page.evaluate(()=>app.isCapturingSequence)).toBe(false);
});

test('frame timeout is explicit, stops capture safely and recovers without a camera reconnect',async({page,context})=>{
  await context.addCookies(cookies);await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  let connects=0,stalled=true;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/camera/connect'))connects++;});
  await page.route('**/camera/frame',async route=>{
    if(stalled){await new Promise(resolve=>setTimeout(resolve,4500));await route.abort().catch(()=>{});}
    else await route.fallback();
  });
  await expect(page.locator('#hostCameraStatus')).toContainText('Live preview timed out',{timeout:9000});
  stalled=false;await page.waitForFunction(()=>app.hostPreviewHealthy);
  expect(connects).toBe(0);
  expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(0);
  expect(await page.evaluate(()=>app.isCapturingSequence)).toBe(false);
});

for(const origin of ['http://172.20.10.2:8000','http://192.168.43.23:8000'])test(`built Guest requests follow DHCP origin ${origin}`,async({page})=>{
  const requests=[];
  page.on('request',r=>requests.push(r.url()));
  // Simulate two different DHCP networks while running the real built UI and
  // backend. There is no Vite or localhost URL in the browser's Guest traffic.
  await page.route(origin+'/**',async route=>{
    const url=new URL(route.request().url());
    const response=await route.fetch({url:'http://127.0.0.1:8028'+url.pathname+url.search});
    await route.fulfill({response});
  });
  await page.goto(origin+'/booth');
  await page.locator('#boothPairKey').fill('preview-only-disposable-pairing-key');
  await page.locator('#boothPairForm button').click();
  await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  await page.locator('#frameCardLandscape4').click();
  await expect.poll(()=>page.evaluate(()=>app.persistenceBusy)).toBe(false);
  await page.evaluate(()=>app.capturePhoto(0));
  expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(1);
  expect(requests.some(url=>url.endsWith('/camera/frame'))).toBe(true);
  expect(requests.some(url=>url.endsWith('/camera/captures'))).toBe(true);
  expect(requests.filter(url=>new URL(url).pathname.startsWith('/api/')).every(url=>new URL(url).origin===origin)).toBe(true);
});
