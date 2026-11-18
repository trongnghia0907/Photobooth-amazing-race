import test from 'node:test';
import assert from 'node:assert/strict';
import {hostPreviewPerformance,prepareHostCamera} from '../src/services/host-camera.js';

test('preview reports measured frame timing, percentiles and lifetime recovery counts',()=>{
  const app={hostPreviewDiagnostics:{frames:140,failedRequests:2,pendingResponses:3,reconnects:1,connectRequests:2,
    samples:Array.from({length:120},(_,i)=>({at:i*125,responseMs:10+i,decodeMs:1,ageUpperBoundMs:12+i}))}};
  const result=hostPreviewPerformance(app);
  assert.equal(result.samples,120);assert.equal(result.displayedFrames,140);
  assert.equal(result.displayedFPS,8);assert.equal(result.reconnects,1);
  assert.equal(result.responseMs.p50,69);assert.equal(result.responseMs.p95,124);assert.equal(result.responseMs.max,129);
  assert.equal(hostPreviewPerformance({}).displayedFPS,null);
});

test('active capture polls progress without requesting previews, reconnects or another shutter',async()=>{
  const previous={fetch:globalThis.fetch,document:globalThis.document,setTimeout:globalThis.setTimeout,clearTimeout:globalThis.clearTimeout};
  const context={id:'session-A',token:'owner-A'},status={textContent:'Capturing',dataset:{}},urls=[],timers=new Map();let serial=0;
  globalThis.document={getElementById:()=>status};
  globalThis.setTimeout=(fn,delay)=>{const id=++serial;timers.set(id,{fn,delay});return id;};
  globalThis.clearTimeout=id=>timers.delete(id);
  globalThis.fetch=async url=>{urls.push(url);return {ok:true,json:async()=>({capture_progress:{capture_id:'capture-A',stage:'receiving_original'},
    camera_progress:{capture_id:'capture-A',stage:'waiting_buffer'}})};};
  const app={cameraSource:'host',sessionContext:context,hostPreviewContext:context,hostPreviewEpoch:1,
    hostPreviewHealthy:false,captureBusy:true,hostCaptureRequestActive:true,currentScreen:'capture'};
  try{
    await assert.rejects(prepareHostCamera(app),/Waiting for the original JPEG/);
    assert.match(status.textContent,/Waiting for the original JPEG/);
    assert.deepEqual(urls,['/api/sessions/session-A/camera/status']);
    const timer=[...timers.values()][0];assert.equal(timer.delay,1000);
    timer.fn();await app.hostFrameRequest;
    assert.deepEqual(urls,['/api/sessions/session-A/camera/status','/api/sessions/session-A/camera/status']);
  }finally{Object.assign(globalThis,previous);}
});

test('progress returned for an old session cannot overwrite the current session UI',async()=>{
  const previous={fetch:globalThis.fetch,document:globalThis.document,setTimeout:globalThis.setTimeout,clearTimeout:globalThis.clearTimeout};
  const a={id:'A',token:'owner-A'},b={id:'B',token:'owner-B'},status={textContent:'B is capturing',dataset:{}};
  let finish;const response=new Promise(resolve=>finish=resolve);
  globalThis.fetch=async()=>response;globalThis.document={getElementById:()=>status};
  globalThis.setTimeout=()=>1;globalThis.clearTimeout=()=>{};
  const app={cameraSource:'host',sessionContext:a,hostPreviewContext:a,hostPreviewEpoch:1,
    hostPreviewHealthy:false,captureBusy:true,hostCaptureRequestActive:true,currentScreen:'capture'};
  try{
    const request=prepareHostCamera(app);app.sessionContext=b;app.hostPreviewEpoch++;
    finish({ok:true,json:async()=>({capture_progress:{stage:'normalizing'}})});
    await assert.rejects(request);
    assert.equal(status.textContent,'B is capturing');
  }finally{Object.assign(globalThis,previous);}
});
