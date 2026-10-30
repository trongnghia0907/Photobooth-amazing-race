import {test,expect} from '@playwright/test';
import {spawn} from 'node:child_process';
import {randomBytes,createHash} from 'node:crypto';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,readdirSync,existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import net from 'node:net';

const root=fileURLToPath(new URL('../../../',import.meta.url));
const python=path.join(root,'backend/.venv/Scripts/python.exe');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function port(){const server=net.createServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const value=server.address().port;await new Promise(resolve=>server.close(resolve));return value;}

test('built same-origin kiosk: six shots + retake + finalize + QR + two copies + Host + four shots + real restart + backup',async({page,context,request})=>{
  mkdirSync(path.join(root,'.tools'),{recursive:true});
  const storage=mkdtempSync(path.join(root,'.tools/phase6-run-'));
  const privatePort=await port(),publicPort=await port(),base=`http://127.0.0.1:${privatePort}`,gateway=`http://127.0.0.1:${publicPort}`;
  const password=randomBytes(24).toString('hex'),pairKey=randomBytes(24).toString('hex');
  const env={...process.env,ADMIN_USERNAME:'event-host',ADMIN_PASSWORD:password,BOOTH_PAIRING_KEY:pairKey,PYTHONUTF8:'1'};
  const lines=[],errors=[],captures=[];let child;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/camera/captures'))captures.push(r.postDataJSON());});
  async function start(){
    child=spawn(python,[path.join(root,'scripts/run_host.py'),'--no-prompt','--port',String(privatePort),'--public-gateway','--public-port',String(publicPort),'--storage-root',storage],{cwd:root,env,windowsHide:true});
    child.stdout.on('data',data=>lines.push(data.toString()));child.stderr.on('data',data=>lines.push(data.toString()));
    for(let i=0;i<150;i++){
      if(child.exitCode!==null)throw Error('Launcher failed: '+lines.slice(-3).join(''));
      try{if((await request.get(gateway+'/healthz',{timeout:1000})).ok()&&existsSync(path.join(storage,'.operator-run.json')))return;}catch{}
      await delay(200);
    }throw Error('Launcher startup timeout');
  }
  async function stop(){
    if(!child||child.exitCode!==null)return;
    const manifest=JSON.parse(readFileSync(path.join(storage,'.operator-run.json'),'utf8'));
    for(const service of manifest.children)writeFileSync(service.stop_file,'stop');
    for(let i=0;i<180&&child.exitCode===null;i++)await delay(200);
    expect(child.exitCode,'graceful launcher stop').toBe(0);
  }
  async function finalized(count){
    await page.evaluate(count=>{app.countdownSeconds=1;app.fullAutoMode=false;if(count===4)app.selectPresetLayout('landscape_4');},count);
    await page.locator('#setupStartCaptureBtn').click();
    await expect(page.locator('body')).toHaveClass(/host-capture-fullscreen/);
    await expect(page.locator('#setupRecentSidebar')).not.toBeVisible();
    await expect(page.locator('#countdownNumber')).toBeVisible();
    await expect.poll(()=>page.evaluate(()=>app.photos.filter(Boolean).length),{timeout:45000}).toBe(count);
    await expect.poll(()=>page.evaluate(()=>app.isCapturingSequence)).toBe(false);
    if(count===6){
      const original=await page.evaluate(()=>app.serverSession.photos[1].id);
      await page.evaluate(()=>app.goToScreen('home'));
      await expect(page.locator('#recentPhotoList button')).toHaveCount(6);
      await expect(page.locator('#recentShotProgress')).toContainText('6 / 6');
      page.once('dialog',dialog=>dialog.dismiss());
      await page.locator('#newSessionButton').click();
      expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(6);
      await page.screenshot({path:path.join(root,'docs/screenshots/phase6-current-session-sidebar.png'),fullPage:true});
      await page.locator('#recentPhotoList button').nth(1).click();
      await expect.poll(()=>page.evaluate(()=>app.serverSession.photos[1].id)).not.toBe(original);
      expect(captures).toHaveLength(7);
    }
    await page.locator('#goToResultBtn').click();
    await page.evaluate(()=>{app.selectedFilter='vivid';app.renderCompositeCanvas();});
    await page.locator('#confirmSessionBtn').click();
    await expect(page.locator('#qrStatusBadge')).toContainText('QR sẵn sàng',{timeout:20000});
    const state=await page.evaluate(()=>({sid:app.sessionContext.id,share:app.activeShare}));
    expect(readdirSync(path.join(storage,'originals',state.sid)).filter(n=>n.endsWith('.png'))).toHaveLength(0);
    expect(readdirSync(path.join(storage,'composites',state.sid)).filter(n=>n.endsWith('.png'))).toHaveLength(1);
    return state;
  }
  try{
    await start();
    await page.goto(base+'/booth');
    await page.locator('#boothPairKey').fill(pairKey);await page.locator('#boothPairForm button').click();
    await page.waitForFunction(()=>app.hostPreviewHealthy);
    await expect(page.locator('#hostCameraPreview')).toHaveClass(/mirror-video/);
    await page.evaluate(()=>app.toggleMirror());
    await expect(page.locator('#hostCameraPreview')).not.toHaveClass(/mirror-video/);
    await page.evaluate(()=>app.toggleMirror());
    await expect(page.locator('#eventCaptureHeading')).toHaveText('AMAZING RACE 2026');
    const geometry=await page.evaluate(()=>{const a=document.getElementById('setupWorkspace').getBoundingClientRect(),b=document.getElementById('setupRecentSidebar').getBoundingClientRect();return {ratio:a.width/(a.width+b.width),left:a.left,right:b.left};});
    expect(geometry.ratio).toBeCloseTo(.75,1);expect(geometry.left).toBeLessThan(geometry.right);
    await page.screenshot({path:path.join(root,'docs/screenshots/phase6-setup-landscape.png'),fullPage:true});
    await page.setViewportSize({width:820,height:1180});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:path.join(root,'docs/screenshots/phase6-setup-portrait.png'),fullPage:true});
    await page.setViewportSize({width:1180,height:820});
    const a=await finalized(6);
    const guest=await context.newPage();
    await guest.goto(a.share.share_url);
    await expect(guest.locator('#guestPhoto')).toBeVisible();
    await guest.reload();await expect(guest.locator('#guestPhoto')).toBeVisible();
    await guest.goto(gateway+new URL(a.share.share_url).pathname);
    await expect(guest.locator('#guestPhoto')).toBeVisible();
    const download=guest.waitForEvent('download');await guest.locator('#guestDownload').click();
    expect((await download).suggestedFilename()).toMatch(/\.png$/);
    const imageA=await request.get(gateway+a.share.download_url);expect(imageA.ok()).toBe(true);
    const digest=createHash('sha256').update(await imageA.body()).digest('hex');
    await page.locator('#printCopies').selectOption('2');await page.locator('#printPhotoBtn').click();
    await expect(page.locator('#printStatus')).toContainText('Mock đã nhận');
    const host=await context.newPage();await host.goto(base+'/admin');
    await host.locator('[name=username]').fill('event-host');await host.locator('[name=password]').fill(password);await host.locator('#login button').click();
    await expect(host.locator('#dashboard')).toBeVisible();
    await expect(host.locator('#gallery').locator('article')).toHaveCount(1);
    await page.evaluate(()=>{app.customTexts.topText='Private name from guest A';});
    await page.locator('#newSessionButton').click();
    await expect(page.locator('#recentEmptyState')).toBeVisible();
    expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(0);
    expect(await page.evaluate(()=>app.customTexts.topText)).toBe('OSA BOOTH');
    expect(await page.locator('#qrExternalUrlInput').inputValue()).toBe('');
    const b=await finalized(4);expect(a.share.share_url).not.toBe(b.share.share_url);expect(captures).toHaveLength(11);
    expect((await request.get(gateway+new URL(a.share.share_url).pathname+'/'+b.sid)).status()).toBe(404);
    await stop();await start();
    for(const state of [a,b]){
      await guest.goto(gateway+new URL(state.share.share_url).pathname);await guest.reload();
      await expect(guest.locator('#guestPhoto')).toBeVisible();
      expect((await request.get(gateway+state.share.download_url)).ok()).toBe(true);
    }
    expect(createHash('sha256').update(await (await request.get(gateway+a.share.download_url)).body()).digest('hex')).toBe(digest);
    await host.reload();await expect(host.locator('#gallery article')).toHaveCount(2);
    await expect(host.locator('#jobs')).toContainText('submitted');
    await expect(host.locator('#jobs')).toContainText('2');
    for(const route of ['/admin','/api/admin/sessions','/api/sessions','/booth','/docs','/.env'])expect((await request.get(gateway+route)).status()).toBe(404);
    expect(errors).toEqual([]);
    await stop();
    const backup=spawn(python,[path.join(root,'scripts/backup_runtime.py'),'--storage-root',storage,'--output',storage+'-backup'],{cwd:root,env,windowsHide:true});
    let backupOutput='';backup.stdout.on('data',d=>backupOutput+=d);backup.stderr.on('data',d=>backupOutput+=d);
    expect(await new Promise(resolve=>backup.on('close',resolve)),backupOutput).toBe(0);
    const manifest=JSON.parse(readFileSync(storage+'-backup/backup-manifest.json','utf8'));
    expect(manifest['.share-key']).toBeTruthy();expect(manifest['photobooth.sqlite3']).toBeTruthy();
    for(const [relative,sha] of Object.entries(manifest))expect(createHash('sha256').update(readFileSync(path.join(storage+'-backup',relative))).digest('hex')).toBe(sha);
  }finally{try{await stop();}finally{writeFileSync(path.join(storage,'test-process.log'),lines.join(''));}}
});
