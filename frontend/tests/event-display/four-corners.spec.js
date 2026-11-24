import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
const ui=new URL('../../../backend/app/event_ui/',import.meta.url);
const artwork=new URL('../../../theme/Theme-display.png',import.meta.url);
const photo=(id,stamp)=>({id,approved_at:stamp,image_url:'/event-display/media/'+id,
  width:stamp%2?800:1200,height:stamp%2?1200:800});
const a=photo('a',1),b=photo('b',2),c=photo('c',3),d=photo('d',4),e=photo('e',5),f=photo('f',6),g=photo('g',7),h=photo('h',8);
async function fixture(page,initial){
  const state={items:initial,offline:false,blocked:new Set(),downloads:[]};
  await page.route('http://gallery.test/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/api/photos'))return state.offline?route.abort():route.fulfill({json:{items:state.items}});
    if(path==='/event-display/assets/theme-display.png')return route.fulfill({contentType:'image/png',body:readFileSync(artwork)});
    if(path.includes('/media/')){
      const id=path.split('/').at(-1);
      state.downloads.push(id);
      if(state.blocked.has(id))return route.fulfill({status:404});
      const {width,height}=state.items.find(item=>item.id===id);
      return route.fulfill({contentType:'image/svg+xml',body:`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="100%" height="100%" fill="#154965"/></svg>`});
    }
    const name=path.endsWith('.js')?'display.js':path.endsWith('.css')?'display.css':'index.html';
    return route.fulfill({contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html',body:readFileSync(new URL(name,ui))});
  });
  await page.goto('http://gallery.test/event-display');return state;
}
const ids=page=>page.locator('#photoWall figure').evaluateAll(nodes=>nodes.map(node=>node.dataset.photoId||null));
async function shown(page,expected){await expect.poll(()=>ids(page)).toEqual(expected);await expect(page.locator('.fading')).toHaveCount(0);}

test('three columns and two rows, latest six photos, oldest replacement on the next photo',async({page})=>{
  const state=await fixture(page,[g,f,e,d,c,b,a]);await shown(page,['b','c','d','e','f','g']);
  await expect(page.locator('#displayLogin')).toBeHidden();
  await expect(page.locator('html')).toHaveAttribute('lang','en');
  await expect(page.locator('#photoWall figure')).toHaveCount(6);
  expect(await page.locator('#photoWall img').evaluateAll(images=>images.map(i=>i.naturalWidth/i.naturalHeight))).toEqual([1.5,2/3,1.5,2/3,1.5,2/3]);
  await expect(page.locator('#displayPresentation button,#displayPresentation select')).toHaveCount(0);
  for(const viewport of [{width:1366,height:690},{width:1280,height:800},{width:1920,height:1080}]){
    await page.setViewportSize(viewport);
    const boxes=await page.locator('#photoWall figure').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};}));
    for(let col=0;col<3;col++){
      expect(boxes[col].x).toBe(boxes[col+3].x);
      expect(boxes[col].y).toBe(boxes[0].y);
      expect(boxes[col+3].y).toBe(boxes[3].y);
    }
    for(const box of boxes){
      expect(box.w).toBeGreaterThan(viewport.width*.27);
      expect(box.h).toBeGreaterThan(viewport.height*.40);
      expect(box.w).toBeCloseTo(boxes[0].w,0);
      expect(box.h).toBeCloseTo(boxes[0].h,0);
    }
    expect(boxes[0].x+boxes[0].w).toBeLessThan(boxes[1].x);
    expect(boxes[1].x+boxes[1].w).toBeLessThan(boxes[2].x);
    expect(boxes[0].x).toBeCloseTo(viewport.width-boxes[2].x-boxes[2].w,0);
    expect(boxes[0].y+boxes[0].h).toBeLessThan(boxes[3].y);
    const themeTop=await page.locator('.official-event-art').evaluate(el=>parseFloat(getComputedStyle(el).backgroundPositionY));
    expect(themeTop).toBeGreaterThanOrEqual(6);
    expect(boxes[0].y).toBeGreaterThan(themeTop+viewport.width*.045);
    await expect(page.locator('#photoWall figure').first()).toHaveCSS('background-color','rgba(0, 0, 0, 0)');
    await expect(page.locator('#displayStatus')).toBeHidden();
    expect(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight&&document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  expect(await page.locator('#photoWall img').first().evaluate(i=>getComputedStyle(i).objectFit)).toBe('contain');
  await page.evaluate(()=>{window.changes=[];new MutationObserver(records=>{for(const r of records)if(r.target.classList.contains('fading'))window.changes.push(r.target.dataset.slot);}).observe(document.getElementById('photoWall'),{subtree:true,attributes:true,attributeFilter:['class']});});
  state.items=[h,g,f,e,d,c,b,a];await shown(page,['h','c','d','e','f','g']);
  expect(await page.evaluate(()=>window.changes)).toEqual(['0']);
  const before=state.downloads.slice();await page.waitForTimeout(5500);await shown(page,['h','c','d','e','f','g']);expect(state.downloads).toEqual(before);
});

test('empty slots, failed preload preserves image, offline reconnect replay, revocation and page lifecycle cleanup',async({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const state=await fixture(page,[]);await expect(page.locator('#displayEmpty')).toBeVisible();
  state.items=[b,a];await shown(page,['a','b',null,null,null,null]);
  await expect(page.locator('#photoWall img')).toHaveCount(2);
  state.items=[f,e,d,c,b,a];await shown(page,['a','b','c','d','e','f']);
  state.blocked.add('g');state.items=[g,f,e,d,c,b,a];await expect.poll(()=>state.downloads.includes('g')).toBe(true);await shown(page,['a','b','c','d','e','f']);
  state.offline=true;await expect(page.locator('#displayStatus')).toContainText('Connection lost');await shown(page,['a','b','c','d','e','f']);
  state.blocked.delete('g');state.items=[h,g,f,e,d,c,b,a];state.offline=false;await shown(page,['g','h','c','d','e','f']);
  state.items=[h,g,f,e,d,b,a];await shown(page,['g','h',null,'d','e','f']);
  // A reapproval is a new publication even when the image ID is unchanged.
  state.items=[photo('c',9),h,g,f,e,d,b,a];await shown(page,['g','h','c','d','e','f']);
  await page.evaluate(()=>dispatchEvent(new PageTransitionEvent('pagehide')));
  const count=state.downloads.length;await page.waitForTimeout(3000);expect(state.downloads).toHaveLength(count);
  await page.evaluate(()=>dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true})));
  await shown(page,['d','e','f','g','h','c']);expect(errors).toEqual([]);
});
