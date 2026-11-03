import {test,expect} from '@playwright/test';
import {spawn} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {mkdtempSync,mkdirSync,existsSync,readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import net from 'node:net';

const root=fileURLToPath(new URL('../../../',import.meta.url));
const python=process.env.PHOTOBOOTH_PYTHON||path.join(root,process.platform==='win32'?'backend/.venv/Scripts/python.exe':'backend/.venv/bin/python');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function freePort(){const server=net.createServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const port=server.address().port;await new Promise(resolve=>server.close(resolve));return port;}

test('rehearsal recovers shots and final after reload, resets only confirmed idle sessions, and event UI blocks unverified camera',async({page,request})=>{
  mkdirSync(path.join(root,'.tools'),{recursive:true});
  const storage=mkdtempSync(path.join(root,'.tools/readiness-run-')),port=await freePort(),base=`http://127.0.0.1:${port}`;
  const pair=randomBytes(24).toString('hex'),env={...process.env,APP_ENV:'development',OPERATION_MODE:'rehearsal',ALLOW_MOCK_HARDWARE:'true',
    ADMIN_USERNAME:'readiness-test',ADMIN_PASSWORD:randomBytes(24).toString('hex'),BOOTH_PAIRING_KEY:pair,
    PUBLIC_BASE_URL:base,GUEST_SESSION_IDLE_SECONDS:'5',PRINTER_MODE:'mock',ENABLE_PHYSICAL_PRINTING:'false',PYTHONUTF8:'1'};
  const child=spawn(python,[path.join(root,'scripts/run_host.py'),'--no-prompt','--mode','rehearsal','--allow-mock-hardware','--port',String(port),'--storage-root',storage],{cwd:root,env,windowsHide:true});
  const lines=[],errors=[];let captureRequests=0,sessionCreates=0;
  child.stdout.on('data',data=>lines.push(data.toString()));child.stderr.on('data',data=>lines.push(data.toString()));
  page.on('pageerror',error=>errors.push(error.message));page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/camera/captures'))captureRequests++;if(r.method()==='POST'&&r.url().endsWith('/api/sessions'))sessionCreates++;});
  try{
    for(let i=0;i<150;i++){
      if(child.exitCode!==null)throw new Error('Launcher stopped: '+lines.slice(-3).join(''));
      try{if((await request.get(base+'/api/health',{timeout:1000})).ok()&&existsSync(path.join(storage,'.operator-run.json')))break;}catch{}
      await pause(200);
    }
    await page.goto(base+'/booth');await page.locator('#boothPairKey').fill(pair);await page.locator('#boothPairForm button').click();
    await page.waitForFunction(()=>app.hostPreviewHealthy&&app.eventConfigurationReady);
    await page.evaluate(()=>app.showToast('<img src=x onerror="window.toastInjection=true">','info'));
    await expect(page.locator('#toastContainer img')).toHaveCount(0);
    expect(await page.evaluate(()=>window.toastInjection)).toBeUndefined();
    await expect(page.locator('#demoModeBadge')).toContainText('DEMO');
    await page.evaluate(()=>{app.selectPresetLayout('landscape_4');app.countdownSeconds=1;});
    await page.locator('#setupStartCaptureBtn').click();
    await expect(page.locator('body')).toHaveAttribute('data-workflow','review',{timeout:45000});
    const sid=await page.evaluate(()=>app.sessionContext.id),photos=await page.evaluate(()=>app.serverSession.photos.map(photo=>photo.id));
    await page.waitForTimeout(5500); // Deliberately exceed idle timeout while still unconfirmed.
    expect(await page.evaluate(()=>app.sessionContext.id)).toBe(sid);
    expect(await page.evaluate(()=>app.photos.filter(Boolean).length)).toBe(4);
    await page.reload();await expect(page.locator('body')).toHaveAttribute('data-workflow','review');
    expect(await page.evaluate(()=>app.serverSession.photos.map(photo=>photo.id))).toEqual(photos);
    expect(await page.evaluate(()=>app.serverSession.finalized)).toBe(false);
    await expect(page.locator('#guestReviewShots button')).toHaveCount(4);
    expect(captureRequests).toBe(4);
    await page.locator('#confirmSessionBtn').click();await expect(page.locator('#qrStatusBadge')).toContainText('QR sẵn sàng');
    const share=await page.evaluate(()=>app.activeShare.share_url);
    await page.reload();await expect(page.locator('#qrStatusBadge')).toContainText('QR sẵn sàng');
    expect(await page.evaluate(()=>app.activeShare.share_url)).toBe(share);
    expect(await page.evaluate(()=>app.sessionContext.id)).toBe(sid);
    await expect(page.locator('body')).toHaveAttribute('data-workflow','setup',{timeout:10000});
    expect(await page.evaluate(()=>app.sessionContext)).toBe(null);
    expect(await page.evaluate(()=>sessionStorage.getItem('amazing-race-session-v1'))).toBe(null);

    // Test the guest presentation contract with an explicitly simulated server
    // configuration; backend Event capability enforcement has separate tests.
    await page.route('**/api/booth/config',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({
      operation_mode:'event',event_mode:true,mock_hardware_allowed:false,guest_idle_seconds:0,gallery_poll_seconds:5})}));
    await page.reload();await expect(page.locator('body')).toHaveAttribute('data-event-mode','true');
    await expect(page.locator('#demoModeBadge')).toBeHidden();
    await expect(page.locator('#setupCameraStatus')).toContainText('Camera chưa sẵn sàng');
    await expect(page.locator('#hostCameraTools')).toBeHidden();await expect(page.locator('#setupDeviceOptions')).toBeHidden();
    await page.locator('#setupStartCaptureBtn').click();
    await expect(page.locator('#sessionSaveStatus')).toContainText('nhân viên hỗ trợ');
    expect(captureRequests).toBe(4);
    await page.screenshot({path:path.join(root,'docs/screenshots/event-clean-blocked.png'),fullPage:true});
    const createdBeforeCorruption=sessionCreates;
    await page.evaluate(()=>sessionStorage.setItem('amazing-race-session-v1','{broken'));
    await page.reload();await page.waitForFunction(()=>app.resumeRecoveryPending);
    await expect(page.locator('#setupStartCaptureBtn')).toBeDisabled();
    expect(sessionCreates).toBe(createdBeforeCorruption);
    expect(errors).toEqual([]);
  }finally{
    const manifest=path.join(storage,'.operator-run.json');
    if(existsSync(manifest))for(const service of JSON.parse(readFileSync(manifest,'utf8')).children)writeFileSync(service.stop_file,'stop');
    for(let i=0;i<180&&child.exitCode===null;i++)await pause(200);
    writeFileSync(path.join(storage,'test-process.log'),lines.join(''));
    expect(child.exitCode,'graceful owned launcher shutdown').toBe(0);
  }
});
