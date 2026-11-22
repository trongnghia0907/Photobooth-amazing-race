import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';

const ui=new URL('../../../backend/app/gallery_ui/',import.meta.url);
const artwork=new URL('../../../theme/theme-gallery.png',import.meta.url);
function items(count){return Array.from({length:count},(_,index)=>({id:'photo-'+(count-index),
  preview_url:'/gallery/preview/photo-'+(count-index),photo_url:'/gallery/photo/photo-'+(count-index),
  width:index%2?1200:800,height:index%2?800:1200,
  expires_at:new Date(Date.now()+3600000).toISOString()}));}
async function fixture(page,initial){
  const state={items:initial,offline:false,apiCalls:0,previewRequests:0};
  const thumbnails=(await page.evaluate(()=>[[40,60],[60,40]].map(([width,height])=>{
    const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    canvas.getContext('2d').fillRect(0,0,width,height);return canvas.toDataURL().split(',')[1];
  }))).map(value=>Buffer.from(value,'base64'));
  await page.route('http://gallery.test/**',async route=>{
    const url=new URL(route.request().url()),path=url.pathname;
    if(path==='/gallery/api/photos'){
      state.apiCalls++;if(state.offline)return route.abort();
      const pages=Math.max(1,Math.ceil(state.items.length/10));
      const pageNumber=Math.min(pages,Math.max(1,parseInt(url.searchParams.get('page'),10)||1));
      return route.fulfill({json:{items:state.items.slice((pageNumber-1)*10,pageNumber*10),total:state.items.length,page:pageNumber,pages,page_size:10}});
    }
    if(path.startsWith('/gallery/preview/')){
      state.previewRequests++;
      const item=state.items.find(item=>item.preview_url===path);
      return route.fulfill({contentType:'image/png',body:thumbnails[item?.width>item?.height?1:0]});
    }
    if(path==='/gallery/assets/theme-gallery.png')return route.fulfill({contentType:'image/png',body:readFileSync(artwork)});
    const name=path.endsWith('.js')?'gallery.js':path.endsWith('.css')?'gallery.css':'index.html';
    return route.fulfill({contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html',body:readFileSync(new URL(name,ui))});
  });
  return state;
}

test('public gallery: wide desktop, actual pagination, preserved page and responsive contained photos',async({page})=>{
  await page.clock.install();await page.setViewportSize({width:1920,height:1080});
  const state=await fixture(page,items(23));await page.goto('http://gallery.test/gallery');
  const cards=page.locator('#photoGrid .photo-card');await expect(cards).toHaveCount(10);
  await expect(page.locator('#galleryStatus')).toHaveCount(0);
  await expect(page.locator('#galleryFeedback')).toBeHidden();
  expect(await page.locator('#photoGrid').evaluate(grid=>grid.previousElementSibling===null)).toBe(true);
  await page.clock.runFor(100);
  await expect.poll(()=>cards.first().locator('img').evaluate(img=>img.complete&&img.naturalWidth>0)).toBe(true);
  await expect(cards.first().locator('img')).toBeVisible();
  await expect.poll(()=>cards.locator('img').evaluateAll(images=>images.slice(0,2).map(img=>img.naturalWidth/img.naturalHeight))).toEqual([2/3,1.5]);
  await expect(cards.first()).toHaveCSS('background-color','rgba(0, 0, 0, 0)');
  await expect(cards.first()).toHaveCSS('border-top-width','0px');
  await expect(cards.first()).toHaveCSS('padding','0px');
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
  await expect(page.locator('#pagination [aria-current=page]')).toHaveText('2');
  expect(state.previewRequests).toBe(downloads);
  state.offline=true;await page.clock.fastForward(16000);
  await expect(page.locator('#retryGallery')).toBeVisible();
  state.offline=false;await page.locator('#retryGallery').click();
  await expect(page.locator('#pagination [aria-current=page]')).toHaveText('2');await expect(page).toHaveURL(/page=2$/);
  await page.getByRole('link',{name:'Next page',exact:true}).click();await expect(cards).toHaveCount(3);
  await page.reload();await expect(page.locator('#pagination [aria-current=page]')).toHaveText('3');
  await page.goto('http://gallery.test/gallery?page=99999');await expect(page).toHaveURL(/page=3$/);
  await page.goto('http://gallery.test/gallery?page=invalid');await expect(cards).toHaveCount(10);await expect(page).toHaveURL(/page=1$/);
  for(const [width,columns] of [[1920,5],[1440,4],[900,3],[430,2],[360,1]]){
    await page.setViewportSize({width,height:900});
    expect(await page.locator('#photoGrid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length)).toBe(columns);
    const {size,top,gridTop}=await page.evaluate(()=>{
      const art=getComputedStyle(document.body,'::before');
      return {size:art.backgroundSize,top:parseFloat(art.backgroundPositionY),gridTop:document.querySelector('#photoGrid').getBoundingClientRect().top};
    });
    expect(size).toBe('100% auto');expect(top).toBeGreaterThanOrEqual(6);expect(gridTop).toBeGreaterThan(top+width*.045);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  expect(new Set(await cards.evaluateAll(nodes=>nodes.map(n=>n.dataset.photoId))).size).toBe(10);
  state.items=items(1003);await page.goto('http://gallery.test/gallery?page=50');
  await expect(page.locator('#pagination [aria-current=page]')).toHaveText('50');
  await expect(cards).toHaveCount(10);expect(await page.locator('#pagination a').count()).toBeLessThanOrEqual(9);
});

test('empty state, revocation refresh, QR expiry independence and timer cleanup',async({page})=>{
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
  await page.clock.fastForward(5001);await expect(page.locator('.photo-card')).toHaveCount(1);
  state.items=[];await page.clock.fastForward(16000);await expect(page.locator('.photo-card')).toHaveCount(0);
  await expect(page.locator('#galleryEmpty')).toBeVisible();
  await page.evaluate(()=>dispatchEvent(new PageTransitionEvent('pagehide')));
  const calls=state.apiCalls;await page.clock.fastForward(60000);expect(state.apiCalls).toBe(calls);
});
