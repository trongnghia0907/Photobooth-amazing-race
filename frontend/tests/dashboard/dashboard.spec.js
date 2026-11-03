import {test,expect} from '@playwright/test';
import {randomUUID} from 'node:crypto';

async function login(page){
  await page.goto('/admin');
  await page.locator('#login input[name=username]').fill('test-host');
  await page.locator('#login input[name=password]').fill(process.env.OSA_TEST_ADMIN_PASSWORD);
  await page.locator('#login button').click();
  await expect(page.locator('#backendBadge')).toHaveText('Backend online');
}
async function nav(page,name){await page.locator('nav [data-page="'+name+'"]').click();}
async function seed(page,count){
  const png=Buffer.from(await page.evaluate(count=>{const canvas=document.createElement('canvas');canvas.width=count===4?1200:800;canvas.height=count===4?800:1200;const ctx=canvas.getContext('2d');ctx.fillStyle='#2458d3';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.fillStyle='white';ctx.font='34px sans-serif';ctx.fillText('AMAZING RACE 2026',40,70);return canvas.toDataURL().split(',')[1];},count),'base64');
  const headers=()=>({Authorization:'Bearer '+'a'.repeat(64),'Idempotency-Key':randomUUID()});
  const api=page.request;
  const created=await api.post('/api/sessions',{headers:headers(),data:{layout:count===4?'landscape_4':'grid2x3',slot_count:count}});
  expect(created.ok()).toBeTruthy();const sid=(await created.json()).session_id;
  let state;
  for(let i=0;i<count;i++){const response=await api.post('/api/sessions/'+sid+'/photos',{headers:headers(),multipart:{slot_index:String(i),source:'demo',file:{name:'capture.png',mimeType:'image/png',buffer:png}}});expect(response.ok()).toBeTruthy();state=await response.json();}
  const composite=await api.put('/api/sessions/'+sid+'/composite',{headers:headers(),multipart:{shots_revision:String(state.shots_revision),editor_json:'{}',file:{name:'composite.png',mimeType:'image/png',buffer:png}}});
  expect(composite.ok()).toBeTruthy();const cid=(await composite.json()).composite.id;
  expect((await api.post('/api/sessions/'+sid+'/complete',{headers:headers(),data:{composite_id:cid}})).ok()).toBeTruthy();
  const final=await api.post('/api/sessions/'+sid+'/finalize',{headers:headers(),data:{composite_id:cid}});expect(final.ok()).toBeTruthy();return sid;
}

test('Host operations: navigation, unsaved forms, diagnostics, frames, photos, reprint, event access and logout',async({page},testInfo)=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await login(page);
  await expect(page.locator('[data-panel]:visible')).toHaveCount(1);
  const first=await seed(page,4);await seed(page,6);
  await expect(page.locator('#kpiCompleted')).toHaveText('2');
  for(const section of ['photos','prints','camera','frames','event','network','system','overview']){
    await nav(page,section);
    await expect(page.locator('[data-panel]:visible')).toHaveAttribute('data-panel',section);
    await expect(page.locator('nav [aria-current=page]')).toHaveAttribute('data-page',section);
  }
  await nav(page,'frames');await page.locator('#frameName').fill('Unsaved event frame');
  await nav(page,'camera');await page.locator('#cameraAdapter').selectOption('vendor');
  await nav(page,'frames');await expect(page.locator('#frameName')).toHaveValue('Unsaved event frame');
  await nav(page,'camera');await expect(page.locator('#cameraAdapter')).toHaveValue('vendor');
  await page.locator('#cameraAdapter').selectOption('mock');await page.locator('#saveCamera').click();
  await page.locator('#refreshCameraDiagnostics').click();
  await expect(page.locator('#cameraDiagnosticChecks tr')).toHaveCount(4);
  await expect(page.locator('#cameraDiagnosticCheckedAt')).not.toHaveText('—');
  await page.locator('#runCameraDiagnostic').click();
  await expect(page.locator('#cameraDiagnosticSummary')).toContainText('completed');
  await page.locator('#cameraAdapter').selectOption('vendor');await page.locator('#saveCamera').click();
  await expect(page.locator('#cameraDiagnosticStale')).toBeVisible();
  await page.locator('#cameraAdapter').selectOption('mock');await page.locator('#saveCamera').click();
  await nav(page,'frames');await page.locator('#frameName').fill('Event frame');await page.locator('#saveFrameConfig').click();
  await expect(page.locator('#frameManagementStatus')).toContainText('Đã lưu');
  await nav(page,'photos');await expect(page.locator('#gallery .photo-card')).toHaveCount(2);
  await page.locator('#gallery button').last().click();
  await expect(page.locator('#sessionInfo')).toContainText(first);
  const download=page.waitForEvent('download');await page.getByRole('link',{name:'Tải composite gốc',exact:true}).click();
  expect((await download).suggestedFilename()).toContain('amazing-race-2026');
  await page.locator('#displayApprovalBasis').selectOption('guest_consent');await page.locator('#displayConsentConfirmed').check();await page.locator('#approveDisplayPhoto').click();
  await expect(page.locator('#hideDisplayPhoto')).toBeVisible();await page.locator('#hideDisplayPhoto').click();await expect(page.locator('#hideDisplayPhoto')).toHaveCount(0);
  await page.getByRole('button',{name:'In lại',exact:true}).click();
  await nav(page,'prints');await expect(page.locator('#jobs tr')).toHaveCount(1);
  await expect(page.locator('#jobs')).toContainText('Submitted');
  await expect(page.locator('#jobs')).toContainText('Mock / DEMO');
  await page.locator('#selectPrinter').click();
  await nav(page,'event');page.once('dialog',dialog=>dialog.accept());await page.locator('#createDisplayCode').click();
  await expect(page.locator('#eventDisplayCode')).toContainText('Mã màn hình');
  await page.locator('#revokeDisplayCode').click();await expect(page.locator('#eventDisplayStatus')).toContainText('chưa được bật');
  await nav(page,'network');await expect(page.locator('#networkRows')).toContainText('PUBLIC_BASE_URL');
  await nav(page,'overview');
  await page.screenshot({path:testInfo.outputPath('overview-desktop.png'),fullPage:true});
  for(const size of [{width:1024,height:768},{width:600,height:900}]){
    await page.setViewportSize(size);await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  await page.setViewportSize({width:1366,height:900});await nav(page,'photos');
  await page.screenshot({path:testInfo.outputPath('gallery-desktop.png'),fullPage:true});
  await nav(page,'system');await page.locator('#logout').click();await expect(page.locator('#login')).toBeVisible();
  expect((await page.request.get('/api/admin/sessions')).status()).toBe(401);
  expect((await page.request.get('/api/admin/camera',{headers:{Authorization:'Bearer '+'a'.repeat(64)}})).status()).toBe(401);
  expect(errors).toEqual([]);
});

test('diagnostic loading, repeated clicks, backend errors and unauthorized session',async({page})=>{
  await login(page);await nav(page,'camera');
  let release;const pending=new Promise(resolve=>{release=resolve;});let calls=0;
  await page.route('**/api/admin/camera/diagnostic',async route=>{calls++;await pending;await route.fulfill({status:504,json:{error:{message:'Diagnostic timeout (test)'}}});});
  await page.locator('#cameraAdvanced summary').click();
  await page.locator('#runCameraDiagnostic').click();
  await expect(page.locator('#runCameraDiagnostic')).toBeDisabled();
  await expect(page.locator('#refreshCameraDiagnostics')).toBeDisabled();
  await page.locator('#runCameraDiagnostic').dispatchEvent('click');expect(calls).toBe(1);
  release();await expect(page.locator('#cameraDiagnosticSummary')).toContainText('Diagnostic timeout');
  await page.route('**/api/admin/camera',route=>route.abort('connectionrefused'));
  await page.locator('#refreshCameraDiagnostics').click();await expect(page.locator('#cameraDiagnosticSummary')).toContainText('failed');
  await page.unroute('**/api/admin/camera');
  await page.route('**/api/admin/camera',route=>route.fulfill({status:401,json:{error:{message:'Host session expired'}}}));
  await page.locator('#refreshCameraDiagnostics').click();await expect(page.locator('#login')).toBeVisible();await expect(page.locator('#dashboard')).toBeHidden();
});
