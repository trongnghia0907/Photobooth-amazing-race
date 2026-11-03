import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';

test('existing finalized demo photo restores public QR and refreshes metadata without uploading another composite',async({page},testInfo)=>{
  const operator=JSON.parse(readFileSync(new URL('../../../.tools/mobile-qr-demo/operator.json',import.meta.url),'utf8'));
  const status=JSON.parse(readFileSync(new URL('../../../.tools/mobile-qr-demo/status.json',import.meta.url),'utf8'));
  expect(status.phase).toBe('running');
  const paired=await page.request.post('/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:operator.pairing_code}});
  expect(paired.ok()).toBeTruthy();
  let uploads=0,finalizes=0;
  page.on('request',request=>{
    if(request.method()==='PUT'&&request.url().endsWith('/composite'))uploads++;
    if(request.method()==='POST'&&request.url().endsWith('/finalize'))finalizes++;
  });
  await page.goto('/booth');
  await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  await page.locator('#frameCardLandscape4').click();
  await expect.poll(()=>page.evaluate(()=>app.persistenceBusy)).toBe(false);
  await page.evaluate(()=>{app.countdownSeconds=1;});
  await page.locator('#setupStartCaptureBtn').click();
  await expect(page.locator('body')).toHaveAttribute('data-workflow','review',{timeout:40000});
  await page.locator('#confirmSessionBtn').click();
  await expect(page.locator('#qrStatusBadge')).toContainText('QR sẵn sàng');
  const share=await page.evaluate(()=>app.activeShare.share_url);
  expect(share.startsWith(status.origin+'/p/')).toBe(true);
  await expect(page.locator('#qrStatusBadge')).toContainText('HTTPS công khai');
  const health=await (await page.request.get('/api/health')).json();
  for(const [state,label] of [['connecting','Tunnel đang kết nối'],['disconnected','Tunnel đã ngắt kết nối']]){
    await page.route('**/api/health',route=>route.fulfill({json:{...health,sharing:{...health.sharing,tunnel_status:state}}}));
    await page.evaluate(()=>app.refreshPublicQR());
    await expect(page.locator('#qrStatusBadge')).toContainText(label);
    await expect(page.locator('#qrExternalUrlInput')).toHaveValue('');
    await page.unroute('**/api/health');
  }
  await page.evaluate(()=>app.refreshPublicQR());
  await expect(page.locator('#qrStatusBadge')).toContainText('HTTPS công khai');
  await expect(page.locator('#qrExternalUrlInput')).toHaveValue(share);
  const sid=await page.evaluate(()=>app.sessionContext.id),uploaded=uploads;
  await page.reload();await expect(page.locator('#qrStatusBadge')).toContainText('QR sẵn sàng');
  expect(await page.evaluate(()=>app.sessionContext.id)).toBe(sid);
  const previous=finalizes;
  await page.locator('#confirmQRCodeBtn').click();
  await expect.poll(()=>finalizes).toBe(previous+1);
  await expect(page.locator('#qrExternalUrlInput')).toHaveValue(share);
  expect(uploads).toBe(uploaded);
  await page.screenshot({path:testInfo.outputPath('public-qr-ready.png'),fullPage:true});
});
