import {test,expect} from '@playwright/test';
import {spawn} from 'node:child_process';
import {randomBytes,randomUUID,createHash} from 'node:crypto';
import {mkdtempSync,mkdirSync,existsSync,readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import net from 'node:net';

const root=fileURLToPath(new URL('../../../',import.meta.url));
const python=process.env.PHOTOBOOTH_PYTHON||path.join(root,process.platform==='win32'?'backend/.venv/Scripts/python.exe':'backend/.venv/bin/python');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function port(){const s=net.createServer();await new Promise(resolve=>s.listen(0,'127.0.0.1',resolve));const n=s.address().port;await new Promise(resolve=>s.close(resolve));return n;}

test('16:9 event display: explicit approval, four-corner gallery, hide, reconnect, revoke and actual backend restart',async({page,browser,request})=>{
  mkdirSync(path.join(root,'.tools'),{recursive:true});
  const storage=mkdtempSync(path.join(root,'.tools/event-gallery-')),p=await port(),base='http://127.0.0.1:'+p;
  const password=randomBytes(24).toString('hex'),pairing=randomBytes(24).toString('hex');
  const env={...process.env,ADMIN_USERNAME:'gallery-host',ADMIN_PASSWORD:password,BOOTH_PAIRING_KEY:pairing,PYTHONUTF8:'1'};
  const log=[],errors=[];let child;
  const step=name=>console.log('[event-display] '+name);
  page.on('pageerror',error=>errors.push(error.message));
  async function start(){
    child=spawn(python,[path.join(root,'scripts/run_host.py'),'--no-prompt','--port',String(p),'--storage-root',storage],{cwd:root,env,windowsHide:true});
    child.stdout.on('data',d=>log.push(String(d)));child.stderr.on('data',d=>log.push(String(d)));
    for(let i=0;i<150;i++){
      if(child.exitCode!==null)throw Error('Launcher failed: '+log.slice(-4).join(''));
      try{if((await request.get(base+'/api/health',{timeout:1000})).ok()&&existsSync(path.join(storage,'.operator-run.json')))return;}catch{}
      await pause(200);
    }throw Error('Startup timeout');
  }
  async function stop(){
    if(!child||child.exitCode!==null)return;
    for(const c of JSON.parse(readFileSync(path.join(storage,'.operator-run.json'),'utf8')).children)writeFileSync(c.stop_file,'stop');
    for(let i=0;i<180&&child.exitCode===null;i++)await pause(200);
    expect(child.exitCode,'graceful host shutdown').toBe(0);
  }
  const hostContext=await browser.newContext({viewport:{width:1280,height:960}}),host=await hostContext.newPage();
  async function code(){
    await host.locator('nav [data-page="event"]').click();
    host.once('dialog',d=>d.accept());await host.locator('#createDisplayCode').click();
    await expect(host.locator('#eventDisplayCode')).toContainText('Mã màn hình');
    return (await host.locator('#eventDisplayCode').textContent()).split(': ').at(-1);
  }
  async function unlock(value){await page.locator('#displayCode').fill(value);await page.locator('#displayLoginForm button').click();await expect(page.locator('#displayPresentation')).toBeVisible();}
  let stationCsrf;
  async function finalPhoto(count,color){
    const auth={Authorization:'Bearer '+randomBytes(32).toString('hex'),'X-Booth-CSRF':stationCsrf};
    const operation=()=>({...auth,'Idempotency-Key':randomUUID()});
    const result=await request.post(base+'/api/sessions',{headers:operation(),data:{layout:count===4?'landscape_4':'grid2x3',slot_count:count}});
    expect(result.ok(),await result.text()).toBe(true);const sid=(await result.json()).session_id;
    const payload=Buffer.from(await page.evaluate(({count,color})=>{
      const c=document.createElement('canvas');c.width=count===4?1200:800;c.height=count===4?800:1200;const x=c.getContext('2d');
      x.fillStyle='#101a2c';x.fillRect(0,0,c.width,c.height);const rows=count/2,w=(c.width-90)/2,h=(c.height-150)/rows;
      for(let i=0;i<count;i++){x.fillStyle=color;x.fillRect(30+(i%2)*(w+30),70+Math.floor(i/2)*(h+15),w,h-10);x.fillStyle='white';x.font='48px sans-serif';x.fillText('PHOTO '+(i+1),55+(i%2)*(w+30),140+Math.floor(i/2)*(h+15));}
      x.fillStyle='white';x.font='28px sans-serif';x.fillText('AMAZING RACE 2026',30,40);return c.toDataURL('image/png').split(',')[1];
    },{count,color}),'base64');
    let state;
    for(let i=0;i<count;i++){
      const r=await request.post(base+'/api/sessions/'+sid+'/photos',{headers:operation(),multipart:{slot_index:String(i),source:'demo',file:{name:'fixture.png',mimeType:'image/png',buffer:payload}}});
      expect(r.ok(),await r.text()).toBe(true);state=await r.json();
    }
    const composite=await request.put(base+'/api/sessions/'+sid+'/composite',{headers:operation(),multipart:{shots_revision:String(state.shots_revision),editor_json:'{}',file:{name:'composite.png',mimeType:'image/png',buffer:payload}}});
    expect(composite.ok(),await composite.text()).toBe(true);
    const body={composite_id:(await composite.json()).composite.id};
    expect((await request.post(base+'/api/sessions/'+sid+'/complete',{headers:operation(),data:body})).ok()).toBe(true);
    const final=await request.post(base+'/api/sessions/'+sid+'/finalize',{headers:operation(),data:body});
    expect(final.ok(),await final.text()).toBe(true);return {sid,...await final.json(),payload};
  }
  async function consent(count,basis){
    await host.locator('nav [data-page="photos"]').click();
    await host.locator('#refreshGallery').click();
    const card=host.locator('#gallery article').filter({hasText:count+' ảnh'});
    await expect(card).toHaveCount(1);await card.locator('button').click();
    await expect(host.locator('#approveDisplayPhoto')).toBeDisabled();
    await host.locator('#displayApprovalBasis').selectOption(basis);
    await expect(host.locator('#approveDisplayPhoto')).toBeDisabled();
    await host.locator('#displayConsentConfirmed').check();await host.locator('#approveDisplayPhoto').click();
    await expect(host.locator('#hideDisplayPhoto')).toBeVisible();
  }
  try{
    step('start');
    await start();
    const paired=await request.post(base+'/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:pairing}});expect(paired.ok()).toBe(true);stationCsrf=(await paired.json()).csrf_token;
    await host.goto(base+'/admin');await host.locator('[name=username]').fill('gallery-host');await host.locator('[name=password]').fill(password);await host.locator('#login button').click();await expect(host.locator('#dashboard')).toBeVisible();
    const firstCode=await code();
    await page.goto(base+'/event-display');await unlock(firstCode);await expect(page.locator('#displayEmpty')).toBeVisible();
    expect((await page.request.get(base+'/api/admin/sessions')).status()).toBe(401);
    step('create six-photo composite');const a=await finalPhoto(6,'#2856a3');
    await pause(2800);await expect(page.locator('#photoWall figure[data-photo-id]')).toHaveCount(0);
    step('approve first photo');await consent(6,'guest_consent');await expect(page.locator('#photoWall figure[data-photo-id]')).toHaveCount(1);
    const oldMedia=await page.locator('#photoWall img').first().getAttribute('src');
    await expect.poll(()=>page.locator('#photoWall img').first().evaluate(i=>[i.naturalWidth,i.naturalHeight])).toEqual([800,1200]);
    step('create four-photo composite');const b=await finalPhoto(4,'#8a3d61');
    await pause(2800);await expect(page.locator('#photoWall figure[data-photo-id]')).toHaveCount(1);
    step('approve second photo');await consent(4,'event_authorization');await expect(page.locator('#photoWall figure[data-photo-id]')).toHaveCount(2);
    await expect.poll(()=>page.locator('#photoWall img').nth(1).evaluate(i=>[i.naturalWidth,i.naturalHeight])).toEqual([1200,800]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    expect(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight)).toBe(true);
    const feed=await page.request.get(base+'/event-display/api/photos');const json=await feed.json();expect(json.items).toHaveLength(2);
    for(const item of json.items)expect(Object.keys(item).sort()).toEqual(['approved_at','height','id','image_url','width']);
    expect(await feed.text()).not.toContain(a.sid);expect(await feed.text()).not.toContain(a.share.share_url);
    await page.screenshot({path:path.join(root,'frontend/test-results/event-display/four-corner-live-1920.png'),fullPage:true});
    await expect(page.locator('#photoWall figure')).toHaveCount(4);
    await expect(page.locator('#displayPresentation button, #displayPresentation select')).toHaveCount(0);
    step('hide first photo');await host.locator('nav [data-page="photos"]').click();await host.locator('#gallery article').filter({hasText:'6 ảnh'}).locator('button').click();await host.locator('#hideDisplayPhoto').click();
    await expect(page.locator('#photoWall figure[data-photo-id]')).toHaveCount(1);expect((await page.request.get(base+oldMedia)).status()).toBe(404);
    const download=await request.get(base+a.share.download_url);expect(download.ok()).toBe(true);expect(createHash('sha256').update(await download.body()).digest('hex')).toBe(a.share.print_ready.sha256);
    step('network loss/recovery');await page.route('**/event-display/api/photos*',route=>route.abort());
    await expect(page.locator('#displayStatus')).toContainText('Mất kết nối');await expect(page.locator('#photoWall figure[data-photo-id]')).toHaveCount(1);
    await page.unroute('**/event-display/api/photos*');await expect(page.locator('#photoWall figure[data-photo-id]')).toHaveCount(1);
    step('reapprove and rotate access');await consent(6,'guest_consent');await expect(page.locator('#photoWall figure[data-photo-id]')).toHaveCount(2);
    const secondCode=await code();expect(secondCode).not.toBe(firstCode);await expect(page.locator('#displayLogin')).toBeVisible();await expect(page.locator('#photoWall figure[data-photo-id]')).toHaveCount(0);
    await unlock(secondCode);await expect(page.locator('#photoWall figure[data-photo-id]')).toHaveCount(2);
    step('restart actual backend');await stop();await start();await expect(page.locator('#photoWall figure[data-photo-id]')).toHaveCount(2);
    const after=await page.request.get(base+'/event-display/api/photos');expect((await after.json()).items.map(i=>i.id).sort()).toEqual(json.items.map(i=>i.id).sort());
    await expect(page.locator('#photoWall')).toBeVisible();
    await host.locator('nav [data-page="event"]').click();await host.locator('#revokeDisplayCode').click();await expect(page.locator('#displayLogin')).toBeVisible();await expect(page.locator('#photoWall figure[data-photo-id]')).toHaveCount(0);
    expect((await request.get(base+b.share.download_url)).ok()).toBe(true);
    expect(errors).toEqual([]);
  }finally{try{await stop();}finally{await hostContext.close();writeFileSync(path.join(storage,'test-process.log'),log.join(''));}}
});
