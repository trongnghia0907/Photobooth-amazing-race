import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';

const ui=new URL('../../../backend/app/gallery_ui/',import.meta.url);
function items(count){return Array.from({length:count},(_,index)=>({id:'photo-'+(count-index),
  preview_url:'/gallery/preview/photo-'+(count-index),photo_url:'/p/existing-token-'+(count-index),
  width:index%2?1200:800,height:index%2?800:1200,
  expires_at:new Date(Date.now()+3600000).toISOString()}));}
async function fixture(page,initial){
  const state={items:initial,offline:false,apiCalls:0,previewRequests:0};
  const png=Buffer.from(await page.evaluate(()=>{
    const canvas=document.createElement('canvas');canvas.width=40;canvas.height=60;
    canvas.getContext('2d').fillRect(0,0,40,60);return canvas.toDataURL().split(',')[1];
  }),'base64');
  await page.route('http://gallery.test/**',async route=>{
    const url=new URL(route.request().url()),path=url.pathname;
    if(path==='/gallery/api/photos'){
      state.apiCalls++;if(state.offline)return route.abort();
      const pages=Math.max(1,Math.ceil(state.items.length/10));
      const pageNumber=Math.min(pages,Math.max(1,parseInt(url.searchParams.get('page'),10)||1));
      return route.fulfill({json:{items:state.items.slice((pageNumber-1)*10,pageNumber*10),total:state.items.length,page:pageNumber,pages,page_size:10}});
    }
    if(path.startsWith('/gallery/preview/')){state.previewRequests++;return route.fulfill({contentType:'image/png',body:png});}
    const name=path.endsWith('.js')?'gallery.js':path.endsWith('.css')?'gallery.css':'index.html';
    return route.fulfill({contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html',body:readFileSync(new URL(name,ui))});
  });
  return state;
}

test('public gallery: five-by-two desktop, actual pagination, preserved page and responsive contained photos',async({page})=>{
  await page.clock.install();await page.setViewportSize({width:1440,height:900});
  const state=await fixture(page,items(23));await page.goto('http://gallery.test/gallery');
  const cards=page.locator('#photoGrid .photo-card');await expect(cards).toHaveCount(10);
  await page.clock.runFor(100);
  await expect.poll(()=>cards.first().locator('img').evaluate(img=>img.complete&&img.naturalWidth>0)).toBe(true);
  await expect(cards.first().locator('img')).toBeVisible();
  expect(await cards.first().getAttribute('data-photo-id')).toBe('photo-23');
  const boxes=await cards.evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};}));
  expect(new Set(boxes.map(b=>b.x)).size).toBe(5);expect(new Set(boxes.map(b=>b.y)).size).toBe(2);
  for(const b of boxes){expect(b.w).toBeCloseTo(boxes[0].w,1);expect(b.h).toBeCloseTo(boxes[0].h,1);}
  expect(await cards.first().locator('img').evaluate(img=>getComputedStyle(img).objectFit)).toBe('contain');
  await page.screenshot({path:'test-results/event-display/public-gallery-desktop.png',fullPage:true});
  await page.getByRole('link',{name:'Page 2',exact:true}).click();
  await expect(cards.first()).toHaveAttribute('data-photo-id','photo-13');
  await expect(page.locator('#pagination [aria-current=page]')).toHaveText('2');
  await expect(page).toHaveURL(/page=2$/);
  const downloads=state.previewRequests;await page.clock.fastForward(16000);
  await expect(page.locator('#galleryStatus')).toContainText('Page 2 of 3');
  expect(state.previewRequests).toBe(downloads);
  state.offline=true;await page.clock.fastForward(16000);
  await expect(page.locator('#retryGallery')).toBeVisible();
  state.offline=false;await page.locator('#retryGallery').click();
  await expect(page.locator('#galleryStatus')).toContainText('Page 2 of 3');await expect(page).toHaveURL(/page=2$/);
  await page.getByRole('link',{name:'Next page',exact:true}).click();await expect(cards).toHaveCount(3);
  await page.reload();await expect(page.locator('#galleryStatus')).toContainText('Page 3 of 3');
  await page.goto('http://gallery.test/gallery?page=99999');await expect(page).toHaveURL(/page=3$/);
  await page.goto('http://gallery.test/gallery?page=invalid');await expect(cards).toHaveCount(10);await expect(page).toHaveURL(/page=1$/);
  for(const [width,columns] of [[900,3],[430,2],[360,1]]){
    await page.setViewportSize({width,height:900});
    expect(await page.locator('#photoGrid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length)).toBe(columns);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  expect(new Set(await cards.evaluateAll(nodes=>nodes.map(n=>n.dataset.photoId))).size).toBe(10);
  state.items=items(1003);await page.goto('http://gallery.test/gallery?page=50');
  await expect(page.locator('#galleryStatus')).toContainText('Page 50 of 101');
  await expect(cards).toHaveCount(10);expect(await page.locator('#pagination a').count()).toBeLessThanOrEqual(9);
});

test('empty state, revocation refresh, expiry removal, network recovery and timer cleanup',async({page})=>{
  await page.clock.install();const state=await fixture(page,[]);await page.goto('http://gallery.test/gallery');
  await expect(page.locator('#galleryEmpty')).toBeVisible();
  state.items=items(11);await page.clock.fastForward(16000);
  await expect(page.locator('.photo-card')).toHaveCount(10);
  state.items=state.items.slice(1);await page.clock.fastForward(16000);
  await expect(page.locator('[data-photo-id="photo-11"]')).toHaveCount(0);
  state.offline=true;await page.clock.fastForward(16000);
  await expect(page.locator('.photo-card')).toHaveCount(0);await expect(page.locator('#retryGallery')).toBeVisible();
  state.offline=false;await page.locator('#retryGallery').click();await expect(page.locator('.photo-card')).toHaveCount(10);
  const expires=await page.evaluate(()=>new Date(Date.now()+5000).toISOString());
  state.items=state.items.slice(0,1).map(item=>({...item,expires_at:expires}));
  await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));
  await expect(page.locator('.photo-card')).toHaveCount(1);
  state.items=[];await page.clock.fastForward(5001);await expect(page.locator('.photo-card')).toHaveCount(0);
  await expect(page.locator('#galleryEmpty')).toBeVisible();
  await page.evaluate(()=>dispatchEvent(new PageTransitionEvent('pagehide')));
  const calls=state.apiCalls;await page.clock.fastForward(60000);expect(state.apiCalls).toBe(calls);
});
