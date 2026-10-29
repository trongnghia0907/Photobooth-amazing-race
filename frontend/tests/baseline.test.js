import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { createApp } from '../src/core/bootstrap.js';
import { createStore } from '../src/core/store.js';
import { layouts, createEmptyPhotos } from '../src/config/layouts.js';

const original = readFileSync(new URL('../../osa_booth_photobooth.html', import.meta.url), 'utf8');
const preserved = readFileSync(new URL('../../legacy/osa_booth_photobooth.original.html', import.meta.url));
const script = original.slice(original.indexOf('    const app = {'), original.indexOf("    window.addEventListener('DOMContentLoaded'"));
const sandbox = { window: {}, console };
vm.runInNewContext(script + '\nglobalThis.baseline = app;', sandbox);
const baseline = sandbox.baseline;
const app = createApp();
const mapping = JSON.parse(readFileSync(new URL('../../docs/function-map.json', import.meta.url)));

test('original and legacy are byte-identical; all 80 methods mapped and callable', () => {
  assert.deepEqual(Buffer.from(original), preserved);
  const methods = Object.keys(baseline).filter(k => typeof baseline[k] === 'function');
  assert.equal(methods.length, 80);
  assert.deepEqual(methods.sort(), mapping.map(f => f.name).sort());
  for (const f of mapping) {
    assert.equal(typeof app[f.name], 'function', f.name);
    assert.match(readFileSync(new URL(`../src/${f.module}.js`, import.meta.url), 'utf8'), new RegExp(`export (?:async )?function ${f.name}\\(`));
  }
});

test('state is isolated, all 9 filters and sticker library retained; auto print off', () => {
  const a = createStore(), b = createStore();
  a.photos[0] = 'fixture';
  assert.equal(b.photos[0], null);
  assert.equal(a.autoPrintPopup, false);
  assert.equal(a.filters.length, 9);
  assert.equal(JSON.stringify(a.filters), JSON.stringify(baseline.filters));
  assert.equal(JSON.stringify(a.stickerLibrary), JSON.stringify(baseline.stickerLibrary));
  assert.equal(createEmptyPhotos('landscape_4').length, 4);
  assert.equal(layouts.landscape_4.enabled, true);
});

test('legacy slot coordinates unchanged for portrait, landscape and detected custom frame', () => {
  for (const [w, h] of [[1200,1800], [1800,1200], [1000,1500]]) {
    assert.equal(JSON.stringify(app.getSixSlotCoordinates(w,h)), JSON.stringify(baseline.getSixSlotCoordinates(w,h)));
  }
  const detected = Array.from({length:6}, (_,i)=>({x:.1+(i%2)*.4,y:.1+Math.floor(i/2)*.25,w:.3,h:.2}));
  app.customFrameImg = baseline.customFrameImg = {width:1000,height:1500};
  app.detectedSlots = baseline.detectedSlots = detected;
  assert.equal(JSON.stringify(app.getSixSlotCoordinates(1000,1500)), JSON.stringify(baseline.getSixSlotCoordinates(1000,1500)));
  app.customFrameImg = baseline.customFrameImg = null;
  app.detectedSlots = baseline.detectedSlots = null;
});

test('canvas algorithms produce same drawing calls as baseline', () => {
  for (const name of ['drawImageCover','roundRectPath','drawBuiltInFrameDecorationsBackground','drawBuiltInFrameForegroundTexts']) {
    const calls = () => {
      const log = [];
      const gradient = {addColorStop: (...args)=>log.push(['addColorStop',...args])};
      const ctx = new Proxy({}, {get:(_,key)=>(...args)=>{log.push([key,...args]); return gradient;},set:(_,key,value)=>{log.push(['set',key,value === gradient ? '[gradient]' : value]);return true;}});
      return {log,ctx};
    };
    const old = calls(), current = calls();
    const args = name === 'drawImageCover' ? [{width:640,height:480},0,0,300,500] : name === 'roundRectPath' ? [1,2,300,500,20] : [1200,1800];
    baseline[name](old.ctx,...args);
    app[name](current.ctx,...args);
    assert.deepEqual(current.log,old.log,name);
  }
  for (const hex of ['#ffffff','#000000','#2563EB','#1E40AF']) assert.equal(app.isColorLight(hex),baseline.isColorLight(hex));
});

test('every original DOM ID remains; styles and dependencies preserved', () => {
  const current = readFileSync(new URL('../index.html',import.meta.url),'utf8');
  const ids = [...original.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);
  for (const id of ids) assert.ok(current.includes(`id="${id}"`),id);
  const css = ['base','components','print'].map(n=>readFileSync(new URL(`../src/styles/${n}.css`,import.meta.url),'utf8')).join('');
  const legacyCss = original.match(/<style>([\s\S]*?)<\/style>/)[1];
  assert.equal(css.replace(/@tailwind (base|components|utilities);/g,'').replace(/\s/g,''), legacyCss.replace(/\s/g,''));
});

test('clearTimers cancels delayed start/next shot/print/QR and interval overlays', () => {
  globalThis.document = {getElementById:()=>({classList:{add(){}}})};
  for (const key of ['sessionStartTimerId','sequenceTimerId','autoPrintTimerId','qrUpdateDebounceTimer']) app[key] = setTimeout(()=>assert.fail(key),100);
  app.countdownTimerId = setInterval(()=>assert.fail('countdown'),100);
  app.autoGraceTimerId = setInterval(()=>assert.fail('grace'),100);
  app.clearTimers();
  for (const key of ['sessionStartTimerId','sequenceTimerId','autoPrintTimerId','qrUpdateDebounceTimer','countdownTimerId','autoGraceTimerId']) assert.equal(app[key],null,key);
  delete globalThis.document;
});
