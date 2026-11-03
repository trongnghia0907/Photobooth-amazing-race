import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
const ui=new URL('../../../backend/app/event_ui/',import.meta.url);
const photo=(id,stamp)=>({id,approved_at:stamp,image_url:'/event-display/media/'+id,width:800,height:1200});
const a=photo('a',1),b=photo('b',2),c=photo('c',3),d=photo('d',4),e=photo('e',5),f=photo('f',6),g=photo('g',7),h=photo('h',8);
async function fixture(page,initial){
  const state={items:initial,offline:false,blocked:new Set(),downloads:[]};
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64');
  await page.route('http://gallery.test/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/api/photos'))return state.offline?route.abort():route.fulfill({json:{items:state.items}});
    if(path.includes('/media/')){const id=path.split('/').at(-1);state.downloads.push(id);return route.fulfill(state.blocked.has(id)?{status:404}:{contentType:'image/png',body:png});}
    const name=path.endsWith('.js')?'display.js':path.endsWith('.css')?'display.css':'index.html';
    return route.fulfill({contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html',body:readFileSync(new URL(name,ui))});
  });
  await page.goto('http://gallery.test/event-display');return state;
}
const ids=page=>page.locator('#photoWall figure').evaluateAll(nodes=>nodes.map(node=>node.dataset.photoId||null));
async function shown(page,expected){await expect.poll(()=>ids(page)).toEqual(expected);await expect(page.locator('.fading')).toHaveCount(0);}

test('four fixed corners, initial latest four, sequential oldest replacement, no timer rotation or duplicate downloads',async({page})=>{
  const state=await fixture(page,[e,d,c,b,a]);await shown(page,['b','c','d','e']);
  await expect(page.locator('#photoWall figure')).toHaveCount(4);
  await expect(page.locator('#displayPresentation button,#displayPresentation select')).toHaveCount(0);
  const boxes=await page.locator('#photoWall figure').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};}));
  expect(boxes[0].x).toBe(boxes[2].x);expect(boxes[1].x).toBe(boxes[3].x);expect(boxes[0].y).toBe(boxes[1].y);expect(boxes[2].y).toBe(boxes[3].y);
  for(const box of boxes){expect(box.w).toBeCloseTo(boxes[0].w,1);expect(box.h).toBeCloseTo(boxes[0].h,1);}
  expect(boxes[0].x+boxes[0].w).toBeLessThan(1920*.4);expect(boxes[1].x).toBeGreaterThan(1920*.6);
  expect(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight&&document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(await page.locator('#photoWall img').first().evaluate(i=>getComputedStyle(i).objectFit)).toBe('contain');
  await page.evaluate(()=>{window.changes=[];new MutationObserver(records=>{for(const r of records)if(r.target.classList.contains('fading'))window.changes.push(r.target.dataset.slot);}).observe(document.getElementById('photoWall'),{subtree:true,attributes:true,attributeFilter:['class']});});
  state.items=[f,e,d,c,b,a];await shown(page,['f','c','d','e']);
  expect(await page.evaluate(()=>window.changes)).toEqual(['0']);
  state.items=[h,g,f,e,d,c,b,a];await shown(page,['f','g','h','e']);
  const before=state.downloads.slice();await page.waitForTimeout(5500);await shown(page,['f','g','h','e']);expect(state.downloads).toEqual(before);
  expect(new Set(await ids(page)).size).toBe(4);
  await page.screenshot({path:'test-results/event-display/four-corners-1920.png'});
});

test('empty slots, failed preload preserves image, offline reconnect replay, revocation and page lifecycle cleanup',async({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const state=await fixture(page,[]);await expect(page.locator('#displayEmpty')).toBeVisible();
  state.items=[b,a];await shown(page,['a','b',null,null]);
  state.items=[d,c,b,a];await shown(page,['a','b','c','d']);
  state.blocked.add('e');state.items=[e,d,c,b,a];await expect.poll(()=>state.downloads.includes('e')).toBe(true);await shown(page,['a','b','c','d']);
  state.offline=true;await expect(page.locator('#displayStatus')).toContainText('Connection lost');await shown(page,['a','b','c','d']);
  state.blocked.delete('e');state.items=[f,e,d,c,b,a];state.offline=false;await shown(page,['e','f','c','d']);
  state.items=[f,e,d,b,a];await shown(page,['e','f',null,'d']);
  // A reapproval is a new publication even when the image ID is unchanged.
  state.items=[photo('c',9),f,e,d,b,a];await shown(page,['e','f','c','d']);
  await page.evaluate(()=>dispatchEvent(new PageTransitionEvent('pagehide')));
  const count=state.downloads.length;await page.waitForTimeout(3000);expect(state.downloads).toHaveLength(count);
  await page.evaluate(()=>dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true})));
  await shown(page,['d','e','f','c']);expect(errors).toEqual([]);
});
