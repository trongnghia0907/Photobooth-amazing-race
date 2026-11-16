import test from 'node:test';
import assert from 'node:assert/strict';
import {hostPreviewPerformance} from '../src/services/host-camera.js';

test('preview reports measured frame timing, percentiles and lifetime recovery counts',()=>{
  const app={hostPreviewDiagnostics:{frames:140,failedRequests:2,pendingResponses:3,reconnects:1,connectRequests:2,
    samples:Array.from({length:120},(_,i)=>({at:i*125,responseMs:10+i,decodeMs:1,ageUpperBoundMs:12+i}))}};
  const result=hostPreviewPerformance(app);
  assert.equal(result.samples,120);assert.equal(result.displayedFrames,140);
  assert.equal(result.displayedFPS,8);assert.equal(result.reconnects,1);
  assert.equal(result.responseMs.p50,69);assert.equal(result.responseMs.p95,124);assert.equal(result.responseMs.max,129);
  assert.equal(hostPreviewPerformance({}).displayedFPS,null);
});
