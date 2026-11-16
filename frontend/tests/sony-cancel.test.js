import test from 'node:test';
import assert from 'node:assert/strict';
import {captureHostPhoto,retryHostCapture} from '../src/services/host-camera.js';

test('operator cancellation clears pending retry only, preserves saved photos and never captures again',async()=>{
  const previous={document:globalThis.document,fetch:globalThis.fetch,sessionStorage:globalThis.sessionStorage};
  const context={id:'test-session',token:'test-owner'},saved={original:'saved image'};
  let requests=0,errors=0;
  globalThis.document={getElementById:()=>({dataset:{},textContent:'',hidden:false})};
  globalThis.sessionStorage={setItem(){}};
  globalThis.fetch=async()=>{requests++;return {ok:false,json:async()=>({error:{code:'capture_cancelled',message:'Cancelled by operator'}})};};
  const app={hostCaptureOperation:{slot:0,key:'old-key',submitted:true},sessionContext:context,photos:[null,saved,null,null],
    cameraSource:'host',ensureSession:async()=>context,syncHostCaptureUI(){},syncPersistenceUI(){},updateCaptureScreenUI(){},
    transitionSession(){},showToast(){},reportSaveError(){errors++;}};
  context.cameraCapture={...app.hostCaptureOperation};
  app.captureHostPhoto=slot=>captureHostPhoto(app,slot);
  try{
    await retryHostCapture(app);
    assert.equal(requests,1);assert.equal(errors,0);
    assert.equal(app.hostCaptureOperation,null);assert.equal(context.cameraCapture,undefined);
    assert.equal(app.photos[1],saved);assert.equal(app.captureBusy,false);assert.equal(app.persistenceError,'');
  }finally{Object.assign(globalThis,previous);}
});
