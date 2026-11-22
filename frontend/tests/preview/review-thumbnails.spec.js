import {test,expect,request} from '@playwright/test';

let cookies;
test.beforeAll(async()=>{
  const client=await request.newContext({baseURL:'http://127.0.0.1:5188'});
  const response=await client.post('/api/booth/pair',{headers:{'X-OSA-Pair':'1'},data:{key:'preview-only-disposable-pairing-key'}});
  expect(response.ok()).toBe(true);
  cookies=(await client.storageState()).cookies;
  await client.dispose();
});
test.afterEach(async({page})=>{
  await page.evaluate(async()=>{app.releaseHostCamera();await app.hostReleaseRequest;}).catch(()=>{});
});

for(const viewport of [{width:1024,height:768},{width:1366,height:768},{width:1920,height:1080},{width:390,height:844}]){
  for(const count of [4,6])test(`Review thumbnails: ${count} photos at ${viewport.width}x${viewport.height}`,async({page,context})=>{
    await context.addCookies(cookies);
    await page.setViewportSize(viewport);
    await page.goto('/');
    await page.waitForFunction(()=>window.app?.hostPreviewHealthy);
    // Isolated, unconfirmed Review fixture: no capture, upload or finalization.
    await page.evaluate(count=>{
      app.slotCount=count;app.presetLayout=count===4?'landscape_4':'grid2x3';
      app.photos=Array.from({length:count},(_,index)=>{
        const canvas=document.createElement('canvas');
        canvas.width=index%2?300:400;canvas.height=index%2?400:300;
        const ctx=canvas.getContext('2d');ctx.fillStyle=index%2?'#1e40af':'#0284c7';ctx.fillRect(0,0,canvas.width,canvas.height);
        ctx.fillStyle='white';ctx.font='40px sans-serif';ctx.fillText('PHOTO '+(index+1),20,70);
        return canvas;
      });
      app.pendingPhotos=Array(count).fill(null);app.guestWorkflowActive=true;
      app.goToScreen('result');
    },count);
    const buttons=page.locator('#guestReviewShots button');
    await expect(buttons).toHaveCount(count);
    await expect(page.locator('#guestReviewProgress')).toHaveText(`${count} / ${count} photos captured`);
    await expect(page.locator('#guestCapturedPanel h2')).toHaveText('Captured Photos');
    await expect(page.locator('#guestReviewEditor,#tabPanel_stickers,#stickerCategoryBar,#stickerItemsGrid')).toHaveCount(0);
    await expect(page.getByText('Drag stickers to move them')).toHaveCount(0);
    await expect(page.locator('#tabBtn_filters,#tabBtn_color,#tabBtn_text,#tabPanel_filters,#tabPanel_color,#tabPanel_text')).toHaveCount(0);
    await expect(page.locator('#setupRecentSidebar').locator('xpath=..')).toHaveAttribute('id','screenHome');
    await expect(page.locator('#screenHome')).toBeHidden();
    const metrics=await page.evaluate(()=>{
      const rect=id=>{const r=document.getElementById(id).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom,right:r.right};};
      const canvas=document.getElementById('compositeCanvas'),main=document.querySelector('main');
      return {panel:rect('guestCapturedPanel'),row:rect('guestReviewShots'),
        preview:rect('guestCompositeCard'),canvas:rect('compositeCanvas'),ratio:canvas.width/canvas.height,
        confirm:rect('confirmSessionBtn'),
        grid:getComputedStyle(document.getElementById('guestReviewShots')).gridTemplateColumns,
        images:[...document.querySelectorAll('#guestReviewShots img')].map(img=>{
          const r=img.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,fit:getComputedStyle(img).objectFit};
        }),horizontalOverflow:document.documentElement.scrollWidth>innerWidth,
        verticalOverflow:document.documentElement.scrollHeight>innerHeight+1||main.scrollHeight>main.clientHeight+1};
    });
    expect(metrics.horizontalOverflow).toBe(false);
    expect(metrics.canvas.width/metrics.canvas.height).toBeCloseTo(metrics.ratio,2);
    if(viewport.width<700&&count===4)expect(metrics.canvas.width).toBeGreaterThan(viewport.width*.9);
    else expect(metrics.canvas.height).toBeGreaterThan(viewport.height*.35);
    for(const image of metrics.images){
      expect(image.height).toBeGreaterThanOrEqual(100);
      expect(image.fit).toBe('contain');
    }
    expect(metrics.images[0].y).toBe(metrics.images[1].y);
    expect(metrics.images.at(-1).y).toBeGreaterThan(metrics.images[0].y);
    expect(new Set(metrics.images.map(image=>image.y)).size).toBe(count/2);
    if(viewport.width>=960){
      expect(metrics.verticalOverflow).toBe(false);
      expect(metrics.panel.x).toBeGreaterThanOrEqual(metrics.preview.right);
      expect(metrics.panel.y).toBeCloseTo(metrics.preview.y,0);
      expect(metrics.preview.width/(metrics.preview.width+metrics.panel.width)).toBeCloseTo(.63,2);
    }else{
      expect(metrics.panel.y).toBeGreaterThanOrEqual(metrics.preview.bottom);
    }
    expect(metrics.grid.split(' ').length).toBe(2);
    expect(metrics.row.bottom).toBeLessThanOrEqual(metrics.panel.bottom);
    expect(await page.locator('#guestReviewShots .guest-review-number').allTextContents()).toEqual(Array.from({length:count},(_,i)=>`#${i+1}`));
    expect(metrics.confirm.y).toBeGreaterThanOrEqual(metrics.canvas.bottom-1);
    expect(metrics.confirm.y-metrics.canvas.bottom).toBeLessThanOrEqual(16);
    expect(metrics.confirm.bottom).toBeLessThanOrEqual(viewport.height);
    await expect(page.locator('#confirmSessionBtn')).toBeVisible();
    await page.screenshot({path:`test-results/preview/review-thumbnails-${count}-${viewport.width}.png`});
    // Original thumbnail button still selects the same slot for retake.
    await buttons.nth(1).click();
    await expect(page.locator('#screenCapture')).toBeVisible();
    expect(await page.evaluate(()=>[app.singleRetakeIndex,app.photos.filter(Boolean).length,app.isCapturingSequence])).toEqual([1,count,false]);
  });
}
