import test from 'node:test';
import assert from 'node:assert/strict';
import {forgetSession} from '../src/services/photo-repository.js';
import {captureHostPhoto} from '../src/services/host-camera.js';
import {photoThumbnail} from '../src/utils/photo-thumbnail.js';

test('New Session can retire a failed camera request but cannot discard an active transfer or browser upload',()=>{
  const previous=globalThis.sessionStorage;globalThis.sessionStorage={removeItem(){}};
  try{
    const make=()=>({hostCaptureOperation:{key:'old'},sessionContext:{id:'A'},pendingPhotos:[null],persistenceError:'timeout',
      stopPrintPolling(){},releaseHostCamera(){assert.equal(this.sessionContext.id,'A');},transitionSession(){},syncPersistenceUI(){},showToast(){}});
    for(const property of ['captureBusy','persistenceBusy','shareBusy','resumeRecoveryPending']){
      const app=make();app[property]=true;assert.equal(forgetSession(app),false);assert.equal(app.sessionContext.id,'A');
    }
    const upload=make();upload.pendingPhotos=[{blob:'unsaved'}];assert.equal(forgetSession(upload),false);
    const app=make();assert.equal(forgetSession(app),true);assert.equal(app.sessionContext,null);
    assert.equal(app.hostCaptureOperation,null);assert.equal(app.persistenceError,'');
  }finally{globalThis.sessionStorage=previous;}
});

test('late capture response stays scoped to the old session and never overwrites new-session state',async()=>{
  const previous={fetch:globalThis.fetch,document:globalThis.document,sessionStorage:globalThis.sessionStorage};
  let reply;const waiting=new Promise(resolve=>reply=resolve);const urls=[];
  globalThis.fetch=async url=>{urls.push(url);await waiting;return {ok:true,json:async()=>({capture:{photo_id:'old-photo'}})};};
  globalThis.document={getElementById:()=>({dataset:{}})};globalThis.sessionStorage={setItem(){}};
  const a={id:'A',token:'owner-A'},b={id:'B',token:'owner-B'},newPhoto={source:'B'};
  const app={hostCaptureOperation:{slot:0,key:'old',submitted:true},sessionContext:a,ensureSession:async()=>a};
  try{
    const pending=captureHostPhoto(app,0);
    await new Promise(resolve=>setImmediate(resolve));
    app.sessionContext=b;app.hostCaptureOperation={slot:0,key:'new'};app.photos=[newPhoto];
    reply();await assert.rejects(pending,{code:'capture_superseded'});
    assert.deepEqual(urls,['/api/sessions/A/camera/captures']);
    assert.equal(app.photos[0],newPhoto);assert.equal(app.hostCaptureOperation.key,'new');
  }finally{Object.assign(globalThis,previous);}
});

test('thumbnail is bounded, preserves ratio, caches immutable canvases and never encodes original pixels',()=>{
  const previous=globalThis.document;let encodes=0;const sizes=[];
  globalThis.document={createElement:()=>({getContext(){return {drawImage:(_s,_x,_y,w,h)=>sizes.push([w,h])};},toDataURL(){encodes++;return 'data:image/jpeg;base64,thumbnail';}})};
  try{
    const source={width:6000,height:4000,toDataURL(){throw new Error('Original must not be encoded');}};
    assert.equal(photoThumbnail(source),photoThumbnail(source));assert.equal(encodes,1);
    assert.deepEqual(sizes,[[640,427]]);
    photoThumbnail({width:4000,height:6000});assert.deepEqual(sizes[1],[427,640]);
    photoThumbnail({width:80,height:60});assert.deepEqual(sizes[2],[80,60]);
  }finally{globalThis.document=previous;}
});
