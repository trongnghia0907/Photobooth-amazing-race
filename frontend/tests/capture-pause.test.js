import test from 'node:test';
import assert from 'node:assert/strict';
import {startOrContinueSequence,runNextShotCountdown} from '../src/features/capture/countdown.js';
import {updateCaptureScreenUI,onAllSixShotsCompleted,captureCurrentFrameImmediately,completePausedCapture} from '../src/features/capture/capture.js';
import {triggerSingleRetake,cancelSingleRetake,resetSessionShots} from '../src/features/capture/retake.js';
import {confirmResetShots} from '../src/features/home/kiosk.js';
import {syncHostCaptureUI,captureHostPhoto,retryHostCapture} from '../src/services/host-camera.js';
import {clearTimers} from '../src/utils/timing.js';
import {readFileSync} from 'node:fs';

async function scenario(count,action){
  const originals={document:globalThis.document,window:globalThis.window,setTimeout:globalThis.setTimeout,clearTimeout:globalThis.clearTimeout,clearInterval:globalThis.clearInterval,performance:globalThis.performance};
  let now=0,serial=0;const timers=new Map(),nodes={};
  const node=()=>{const classes=new Set();return {textContent:'',dataset:{},classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),toggle:(c,on)=>on?classes.add(c):classes.delete(c)},setAttribute(name,value){this[name]=value;}};};
  for(const id of ['countdownOverlay','countdownNumber','countdownLabel','autoGraceOverlay','mainCaptureBtn','mainCaptureBtnText','hostShotProgress','hostCameraStatus','captureProgressTitle','retakeBanner','retakeSlotNumber','cancelRetakeBtn','manualInstantSnapBtn','completeCaptureBtn','resetAllShotsBtn'])nodes[id]=node();
  globalThis.document={getElementById:id=>nodes[id],body:node()};
  globalThis.performance={now:()=>now};
  globalThis.setTimeout=(fn,delay)=>{const id=++serial;timers.set(id,{fn,at:now+delay});return id;};
  globalThis.clearTimeout=globalThis.clearInterval=id=>timers.delete(id);
  const flush=async()=>{for(let i=0;i<10;i++)await Promise.resolve();};
  const advance=async ms=>{const until=now+ms;for(;;){const entry=[...timers.entries()].filter(([,t])=>t.at<=until).sort((a,b)=>a[1].at-b[1].at)[0];if(!entry)break;now=entry[1].at;timers.delete(entry[0]);entry[1].fn();await flush();}now=until;await flush();};
  const shots=[];let reviews=0,preparations=0;
  const app={photos:Array(count).fill(null),slotCount:count,countdownSeconds:3,captureEpoch:0,singleRetakeIndex:null,guestWorkflowActive:true,currentScreen:'capture',
    ensureAudio(){},playBeep(){},hasPendingWork:()=>false,prepareSession:async()=>{preparations++;return true;},transitionSession(){},syncPersistenceUI(){},renderCaptureDots(){},renderSixSlotsGrid(){},showToast(){},
    capturePhoto:async index=>{shots.push(index);app.photos[index]={};return {accepted:true};},
    reportSaveError:error=>{throw error;},finishCaptureAndGoToResult(){assert.ok(app.photos.every(Boolean));reviews++;app.currentScreen='result';clearTimers(app);},
  };
  app.syncHostCaptureUI=()=>syncHostCaptureUI(app);app.updateCaptureScreenUI=()=>updateCaptureScreenUI(app);app.clearTimers=()=>clearTimers(app);
  app.goToScreen=screen=>{app.clearTimers();app.currentScreen=screen;app.updateCaptureScreenUI();};
  app.runNextShotCountdown=()=>runNextShotCountdown(app);app.onAllSixShotsCompleted=()=>onAllSixShotsCompleted(app);
  try{await action({app,nodes,shots,advance,flush,timers,start:()=>startOrContinueSequence(app),reviews:()=>reviews,preparations:()=>preparations});}
  finally{Object.assign(globalThis,originals);}
}

for(const count of [4,6])test(`${count} shots: fractional countdown pause, gap pause, rapid resume and automatic Review`,()=>scenario(count,async({app,nodes,shots,advance,start,reviews,timers})=>{
  await start();await advance(1500);await start();
  assert.equal(nodes.mainCaptureBtnText.textContent,'Tiếp tục chụp');assert.equal(app.countdownState.remainingMs,1500);
  assert.equal(document.body.classList.contains('host-capture-fullscreen'),false);
  assert.equal(nodes.countdownOverlay.classList.contains('hidden'),true);
  const number=nodes.countdownNumber.textContent;await advance(10000);assert.equal(nodes.countdownNumber.textContent,number);assert.equal(shots.length,0);
  await start();assert.equal(nodes.mainCaptureBtnText.textContent,'Tạm dừng');await advance(1499);assert.equal(shots.length,0);await advance(1);assert.deepEqual(shots,[0]);
  await advance(250);await start();assert.equal(app.countdownState.remainingMs,700);await advance(5000);assert.equal(shots.length,1);
  for(let i=0;i<21;i++)await start();assert.equal(app.sequencePaused,false);
  await advance(699);assert.equal(shots.length,1);await advance(1);assert.equal(nodes.countdownNumber.textContent,3);
  await advance(30000);assert.deepEqual(shots,Array.from({length:count},(_,i)=>i));assert.equal(reviews(),1);assert.equal(timers.size,0);
  assert.equal(nodes.hostShotProgress.textContent,`${count} / ${count}`);
}));

for(const count of [4,6])test(`${count} slots: retake waits for action after camera-ready, cancel preserves originals, targeted countdown and instant retake`,()=>scenario(count,async({app,shots,advance,start,flush,reviews})=>{
  const original=Array.from({length:count},()=>({}));app.photos=original.slice();app.currentScreen='result';app.cameraSource='host';
  let connected;app.prepareHostCamera=()=>new Promise(resolve=>{connected=()=>{app.hostPreviewHealthy=true;resolve();};});
  triggerSingleRetake(app,1);assert.equal(app.currentScreen,'capture');await advance(10000);assert.deepEqual(shots,[]);
  connected();await flush();await advance(10000);assert.deepEqual(shots,[]);assert.equal(app.countdownState,null);
  cancelSingleRetake(app);assert.equal(app.currentScreen,'result');assert.deepEqual(app.photos,original);
  triggerSingleRetake(app,1);await start();await advance(3000);assert.deepEqual(shots,[1]);assert.equal(reviews(),1);
  for(let i=0;i<count;i++)if(i!==1)assert.equal(app.photos[i],original[i]);
  const before=app.photos.slice();triggerSingleRetake(app,count-1);
  await captureCurrentFrameImmediately(app);assert.deepEqual(shots,[1,count-1]);assert.equal(app.currentScreen,'result');
  for(let i=0;i<count;i++)if(i!==count-1)assert.equal(app.photos[i],before[i]);
}));

test('paused instant capture takes exactly one, stays interactive, and reset still requires confirmation',()=>scenario(4,async({app,shots,advance,start})=>{
  await start();await advance(1000);await start();
  const first=captureCurrentFrameImmediately(app);await captureCurrentFrameImmediately(app);await first;
  assert.deepEqual(shots,[0]);assert.equal(app.currentScreen,'capture');assert.equal(app.isCapturingSequence,false);
  await advance(10000);assert.deepEqual(shots,[0]);
  app.resetSessionShots=()=>resetSessionShots(app);app.removeStoredPhotos=async()=>{app.photos=Array(4).fill(null);return true;};
  globalThis.window={confirm:()=>false};await confirmResetShots(app);assert.equal(app.photos.filter(Boolean).length,1);
  window.confirm=()=>true;await confirmResetShots(app);assert.equal(app.photos.filter(Boolean).length,0);
}));

test('cancel while camera connects invalidates a pending explicit retake start',()=>scenario(4,async({app,shots,advance,start,flush})=>{
  app.photos=Array.from({length:4},()=>({}));app.currentScreen='result';app.cameraSource='host';
  let ready;const camera=new Promise(resolve=>{ready=resolve;});app.prepareHostCamera=()=>camera;
  triggerSingleRetake(app,2);const pending=start();await flush();cancelSingleRetake(app);ready();await pending;
  await advance(10000);assert.equal(app.currentScreen,'result');assert.deepEqual(shots,[]);
}));

test('last instant shot stays interactive and restarting a full set requires confirmation',()=>scenario(4,async({app,shots,start,reviews})=>{
  app.photos=[{},{},{},null];await captureCurrentFrameImmediately(app);
  assert.deepEqual(shots,[3]);assert.equal(app.currentScreen,'capture');assert.equal(reviews(),0);
  let asked=0;app.confirmResetShots=()=>{asked++;return false;};
  await start();assert.equal(asked,1);assert.equal(app.photos.filter(Boolean).length,4);
}));

test('pause at 1ms before zero, physical capture ignores repeated taps and never duplicates',()=>scenario(4,async({app,nodes,shots,advance,start,flush,timers})=>{
  let release;app.capturePhoto=index=>new Promise(resolve=>{release=()=>{shots.push(index);app.photos[index]={};resolve({accepted:true});};});
  await start();await advance(2999);await start();await advance(8000);assert.equal(shots.length,0);
  await start();await advance(1);assert.equal(app.captureBusy,true);assert.equal(nodes.mainCaptureBtn.disabled,true);
  for(let i=0;i<10;i++)await start();assert.equal(app.sequencePaused,false);
  release();await flush();assert.deepEqual(shots,[0]);assert.equal(nodes.hostShotProgress.textContent,'1 / 4');
  app.clearTimers();await advance(10000);assert.deepEqual(shots,[0]);assert.equal(timers.size,0);
}));

test('rapid initial starts and exit during preparation cannot create duplicate countdowns',()=>scenario(6,async({app,advance,start,timers})=>{
  let release,calls=0;app.prepareSession=()=>{calls++;return new Promise(resolve=>release=resolve);};
  const pending=start();for(let i=0;i<10;i++)await start();assert.equal(calls,1);
  app.clearTimers();release(true);await pending;await advance(20000);assert.equal(app.isCapturingSequence,false);assert.equal(timers.size,0);
}));

test('Guest capture exposes no redundant exit button; Escape cancellation handler remains',()=>{
  const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
  assert.doesNotMatch(html,/id="hostCaptureExit"|Dừng đếm ngược \/ Xem ảnh/);
  assert.match(readFileSync(new URL('../src/features/home/kiosk.js',import.meta.url),'utf8'),/event.key==='Escape'.*app.exitHostCapture/);
});

for(const count of [4,6])test(`${count} paused manual photos: Complete enters Review once with the same saved images`,()=>scenario(count,async({app,nodes,shots,advance,start,reviews,timers})=>{
  app.capturePhoto=async index=>{shots.push(index);app.photos[index]={slot:index,saved:true};return {accepted:true};};
  await start();await advance(1000);await start();
  for(let index=0;index<count;index++){
    assert.equal(nodes.completeCaptureBtn.classList.contains('hidden'),true);
    await captureCurrentFrameImmediately(app);
    assert.equal(app.sequencePaused,true);assert.equal(app.currentScreen,'capture');
  }
  assert.equal(nodes.completeCaptureBtn.classList.contains('hidden'),false);
  assert.equal(nodes.completeCaptureBtn.disabled,false);
  const images=app.photos.slice();await advance(10000);
  assert.equal(reviews(),0);assert.deepEqual(shots,Array.from({length:count},(_,i)=>i));
  completePausedCapture(app);completePausedCapture(app);
  assert.equal(reviews(),1);assert.equal(app.currentScreen,'result');assert.equal(timers.size,0);
  assert.deepEqual(app.photos,images);images.forEach((image,index)=>assert.equal(app.photos[index],image));
}));

test('Complete waits for the final saved image and blocks failures, pending work, retakes and active capture',()=>scenario(4,async({app,nodes,flush,reviews})=>{
  app.photos=[{},{},{},null];app.sequencePaused=true;app.updateCaptureScreenUI();
  let resolve;app.capturePhoto=()=>new Promise(done=>{resolve=done;});
  const pending=captureCurrentFrameImmediately(app);await flush();
  assert.equal(app.captureBusy,true);completePausedCapture(app);assert.equal(reviews(),0);
  resolve({accepted:false});await pending;
  assert.equal(nodes.completeCaptureBtn.classList.contains('hidden'),true);
  completePausedCapture(app);assert.equal(reviews(),0);
  app.capturePhoto=async index=>{app.photos[index]={saved:true};return {accepted:true};};
  await captureCurrentFrameImmediately(app);assert.equal(nodes.completeCaptureBtn.disabled,false);
  app.hasPendingWork=()=>true;app.updateCaptureScreenUI();
  assert.equal(nodes.completeCaptureBtn.disabled,true);completePausedCapture(app);assert.equal(reviews(),0);
  app.hasPendingWork=()=>false;app.singleRetakeIndex=1;app.updateCaptureScreenUI();
  assert.equal(nodes.completeCaptureBtn.classList.contains('hidden'),true);completePausedCapture(app);assert.equal(reviews(),0);
  app.singleRetakeIndex=null;app.isCapturingSequence=true;app.sequencePaused=false;app.updateCaptureScreenUI();
  assert.equal(nodes.completeCaptureBtn.classList.contains('hidden'),true);
  app.sequencePaused=true;app.updateCaptureScreenUI();assert.equal(nodes.completeCaptureBtn.disabled,false);
  completePausedCapture(app);assert.equal(reviews(),1);
}));

for(const count of [4,6])test(`${count} slots: Resume after a paused manual shot captures only missing slots`,()=>scenario(count,async({app,shots,advance,start,reviews})=>{
  await start();await advance(1000);await start();
  await captureCurrentFrameImmediately(app);const first=app.photos[0];
  assert.deepEqual(shots,[0]);assert.equal(app.sequencePaused,true);
  await start();await advance(30000);
  assert.deepEqual(shots,Array.from({length:count},(_,index)=>index));
  assert.equal(app.photos[0],first);assert.equal(reviews(),1);
}));

for(const count of [4,6])for(const paused of [true,false])test(`${count} manual shots, paused=${paused}: failed final transfer retry waits for Complete`,()=>scenario(count,async({app,reviews,nodes})=>{
  app.photos=Array.from({length:count},(_,index)=>index===count-1?null:{slot:index});
  app.cameraSource='host';app.sequencePaused=paused;app.hostPreviewHealthy=false;
  app.prepareHostCamera=async()=>{throw new Error('Test-only camera connection failure');};
  await assert.rejects(captureHostPhoto(app,count-1),/connection failure/);
  app.captureHostPhoto=async slot=>{app.photos[slot]={slot,saved:true};app.hostCaptureOperation=null;};
  await retryHostCapture(app);
  assert.equal(app.currentScreen,'capture');assert.equal(reviews(),0);assert.equal(app.sequencePaused,paused);
  assert.equal(nodes.completeCaptureBtn.disabled,false);
  assert.deepEqual(app.photos.map(photo=>photo.slot),Array.from({length:count},(_,index)=>index));
  completePausedCapture(app);assert.equal(reviews(),1);
}));

for(const retake of [false,true])test(`saved capture retry preserves ${retake?'retake':'automatic'} completion intent`,()=>scenario(4,async({app,reviews})=>{
  app.photos=Array.from({length:4},(_,index)=>index===3?null:{slot:index});app.cameraSource='host';
  app.isCapturingSequence=!retake;app.singleRetakeIndex=retake?3:null;
  app.prepareHostCamera=async()=>{throw new Error('Test-only transfer failure');};
  await assert.rejects(captureHostPhoto(app,3),/transfer failure/);
  app.isCapturingSequence=false;
  app.captureHostPhoto=async slot=>{app.photos[slot]={slot,saved:true};app.hostCaptureOperation=null;};
  await retryHostCapture(app);assert.equal(reviews(),1);assert.equal(app.singleRetakeIndex,null);
}));

for(const count of [4,6])for(const seconds of [3,5,7,10])test(`${count} photos with ${seconds}s countdown capture once per slot`,()=>scenario(count,async({app,advance,start,shots,reviews})=>{
  app.countdownSeconds=seconds;await start();await advance((seconds*1000+1000)*count);
  assert.deepEqual(shots,Array.from({length:count},(_,index)=>index));assert.equal(reviews(),1);
}));
