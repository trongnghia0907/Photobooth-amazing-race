import {test,expect,request} from '@playwright/test';

let cookies;
test.beforeAll(async()=>{
  const api=await request.newContext({baseURL:'http://127.0.0.1:5188'});
  expect((await api.post('/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:'preview-only-disposable-pairing-key'}})).ok()).toBe(true);
  cookies=(await api.storageState()).cookies;await api.dispose();
});

test('Moments has uniform contained frames for mixed composites and keeps cached nodes on polling',async({page,context})=>{
  await context.addCookies(cookies);
  // Synthetic complete composites with old/small and current thumbnail sizes.
  const fixtures=await page.evaluate(()=>[
    [480,320,4],[320,480,6],[240,160,4],[160,240,6],[480,416,4],[264,480,6],
  ].map(([width,height,count],index)=>{
    const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    const ctx=canvas.getContext('2d');ctx.fillStyle='#123c83';ctx.fillRect(0,0,width,height);
    const pad=Math.max(6,width*.035),footer=index>=4?height*.16:0;
    const cellWidth=(width-3*pad)/2,cellHeight=(height-footer-(count/2+2)*pad)/(count/2);
    for(let slot=0;slot<count;slot++){
      ctx.fillStyle=['#43b4cf','#dda570','#8aaab1','#8d9f71','#aa96af','#6f99cd'][slot];
      const x=pad+(slot%2)*(cellWidth+pad),y=pad+(slot>>1)*(cellHeight+pad);
      ctx.fillRect(x,y,cellWidth,cellHeight);ctx.fillStyle='#17374b';ctx.font='bold 18px sans-serif';ctx.fillText('#'+(slot+1),x+8,y+24);
    }
    ctx.fillStyle='#e8f4f8';ctx.fillRect(pad,height-pad-Math.max(footer,pad),width-2*pad,Math.max(footer,pad));
    ctx.fillStyle='#123c83';ctx.font='bold 10px sans-serif';ctx.fillText('AMAZING RACE 2026',pad*1.5,height-pad*1.5);
    return {id:'00000000-0000-4000-8000-'+String(index+1).padStart(12,'0'),width,height,count,png:canvas.toDataURL('image/png').split(',')[1]};
  }));
  let feed=fixtures.slice(0,2);const downloads=[];
  await page.route('**/api/booth/recent-photos?*',route=>route.fulfill({json:{items:feed.map(item=>({id:item.id,width:item.width,height:item.height,
    image_url:'/api/booth/recent-photos/'+item.id+'?thumbnail=true'}))}}));
  await page.route('**/api/booth/recent-photos/*',route=>{
    const item=fixtures.find(item=>route.request().url().includes(item.id));
    if(!item)return route.fulfill({status:404});
    downloads.push(item.id);return route.fulfill({contentType:'image/png',body:Buffer.from(item.png,'base64')});
  });
  await page.goto('/');await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
  const list=page.locator('#recentPhotoList'),cards=list.locator('.recent-gallery-card');
  await expect(cards).toHaveCount(2);
  const original=await cards.first().elementHandle();
  const verify=async()=>{
    const geometry=await cards.evaluateAll(nodes=>nodes.map(card=>{
      const box=card.getBoundingClientRect(),image=card.querySelector('img'),style=getComputedStyle(image);
      return {width:box.width,height:box.height,imageWidth:image.getBoundingClientRect().width,
        fit:style.objectFit,position:style.objectPosition,padding:getComputedStyle(card).padding};
    }));
    for(const card of geometry){
      expect(Math.abs(card.width-card.height)).toBeLessThan(1.5);
      expect(Math.abs(card.width-geometry[0].width)).toBeLessThan(1.5);
      expect(Math.abs(card.height-geometry[0].height)).toBeLessThan(1.5);
      expect(card.imageWidth).toBeGreaterThan(card.width-22);
      expect(card.fit).toBe('contain');expect(card.position).toBe('50% 50%');expect(card.padding).toBe('8px');
    }
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    expect(await list.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  };
  await verify(); // Two entries must not stretch their grid rows to fill the column.
  feed=fixtures;await page.evaluate(()=>app.refreshRecentGallery());await expect(cards).toHaveCount(6);
  for(let i=0;i<fixtures.length;i++){
    const image=cards.nth(i).locator('img');await image.scrollIntoViewIfNeeded();
    await expect.poll(()=>image.evaluate(img=>img.naturalWidth)).toBe(fixtures[i].width);
    expect(await image.evaluate(img=>img.naturalHeight)).toBe(fixtures[i].height);
    await expect(image).toHaveAttribute('loading','lazy');await expect(image).toHaveAttribute('decoding','async');
  }
  const viewports=[{width:1366,height:768},{width:1920,height:1080},{width:1024,height:768},
    {width:1180,height:820},{width:768,height:1024},{width:390,height:844}];
  for(const size of viewports){
    await page.setViewportSize(size);await list.evaluate(el=>el.scrollTop=0);
    await page.evaluate(()=>window.scrollTo(0,0));await verify();
    await page.screenshot({path:`test-results/preview/moments-${size.width}x${size.height}.png`,fullPage:true});
  }
  await page.setViewportSize(viewports[0]);await list.evaluate(el=>el.scrollTop=el.scrollHeight);
  const scroll=await list.evaluate(el=>el.scrollTop);expect(scroll).toBeGreaterThan(0);
  const count=downloads.length;await page.evaluate(()=>app.refreshRecentGallery());
  expect(await list.evaluate(el=>el.scrollTop)).toBe(scroll);expect(downloads.length).toBe(count);
  expect(await original.evaluate(node=>node===document.querySelector('#recentPhotoList img')?.parentElement)).toBe(true);
  expect(await list.locator('img').evaluateAll(nodes=>nodes.map(node=>node.dataset.displayId))).toEqual(fixtures.map(item=>item.id));
  feed=fixtures.filter((_,index)=>index!==1);await page.evaluate(()=>app.refreshRecentGallery());
  await expect(cards).toHaveCount(5);
  await expect(list.locator(`img[data-display-id="${fixtures[1].id}"]`)).toHaveCount(0);
  await page.evaluate(async()=>{app.releaseHostCamera();await app.hostReleaseRequest;});
});
