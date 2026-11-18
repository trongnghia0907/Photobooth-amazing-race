import test from 'node:test';
import assert from 'node:assert/strict';
import {forgetSession} from '../src/services/photo-repository.js';
import {captureHostPhoto,retryHostCapture} from '../src/services/host-camera.js';
import {photoThumbnail} from '../src/utils/photo-thumbnail.js';

test('New Session can retire a failed camera request but cannot discard an active transfer or browser upload',()=>{
  const previous=globalThis.sessionStorage;globalThis.sessionStorage={removeItem(){}};
  try{
    const make=()=>({hostCaptureOperation:{key:'old'},sessionContext:{id:'A'},pendingPhotos:[null],persistenceError:'timeout',
      stopPrintPolling(){},releaseHostCamera(){assert.equal(this.sessionContext.id,'A');},transitionSession(){},syncPersistenceUI(){},showToast(){}});
    for(const property of ['captureBusy','hostCaptureRequestActive','persistenceBusy','shareBusy','resumeRecoveryPending']){
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

test('late response cannot clear a newer capture operation in the same session',async()=>{
  const previous={fetch:globalThis.fetch,document:globalThis.document,sessionStorage:globalThis.sessionStorage};
  let reply;const waiting=new Promise(resolve=>reply=resolve);
  globalThis.fetch=async()=>{await waiting;return {ok:true,json:async()=>({capture:{photo_id:'old-photo'}})};};
  globalThis.document={getElementById:()=>({dataset:{}})};globalThis.sessionStorage={setItem(){}};
  const context={id:'A',token:'owner-A'},old={slot:0,key:'old',submitted:true},current={slot:1,key:'new'};
  const app={hostCaptureOperation:old,sessionContext:context,ensureSession:async()=>context};
  try{
    const pending=captureHostPhoto(app,0);await new Promise(resolve=>setImmediate(resolve));
    app.hostCaptureOperation=current;app.hostCaptureRequestActive=true;
    reply();await assert.rejects(pending,{code:'capture_superseded'});
    assert.equal(app.hostCaptureOperation,current);assert.equal(app.hostCaptureRequestActive,true);
  }finally{Object.assign(globalThis,previous);}
});

test('late preparation error from A cannot overwrite B status or active-request flag',async()=>{
  const previous=globalThis.document;const status={dataset:{},textContent:'B is capturing'};
  globalThis.document={getElementById:()=>status};
  let fail;const preparation=new Promise((_resolve,reject)=>fail=reject);
  const old={slot:0,key:'old',submitted:false},current={slot:0,key:'new'},a={id:'A'},b={id:'B'};
  const app={hostCaptureOperation:old,sessionContext:a,prepareHostCamera:()=>preparation};
  try{
    const pending=captureHostPhoto(app,0);
    app.sessionContext=b;app.hostCaptureOperation=current;app.hostCaptureRequestActive=true;
    const error=Object.assign(new Error('A connection failed'),{code:'disconnected'});fail(error);
    await assert.rejects(pending,error);
    assert.equal(app.hostCaptureOperation,current);assert.equal(app.hostCaptureRequestActive,true);
    assert.equal(status.textContent,'B is capturing');
  }finally{globalThis.document=previous;}
});

test('retired retry callback cannot change B retake state or unlock B capture',async()=>{
  let fail;const request=new Promise((_resolve,reject)=>fail=reject);let updates=0;
  const a={id:'A'},b={id:'B'},old={slot:0,key:'old'},current={slot:1,key:'new'};
  const app={sessionContext:a,hostCaptureOperation:old,captureBusy:false,
    syncHostCaptureUI(){},captureHostPhoto:()=>request,syncPersistenceUI(){updates++;},updateCaptureScreenUI(){updates++;},
    transitionSession(){updates++;},showToast(){updates++;},reportSaveError(){updates++;}};
  const pending=retryHostCapture(app);
  app.sessionContext=b;app.hostCaptureOperation=current;app.singleRetakeIndex=1;app.retakeReturnToReview=true;
  fail(Object.assign(new Error('A was superseded'),{code:'capture_superseded'}));await pending;
  assert.equal(app.captureBusy,true);assert.equal(app.singleRetakeIndex,1);assert.equal(app.retakeReturnToReview,true);
  assert.equal(app.hostCaptureOperation,current);assert.equal(updates,0);
});

test('superseded-session retry directs the guest to New Session rather than another shutter',async()=>{
  let message;const photos=[{saved:'A'}];
  const app={sessionContext:{id:'A'},hostCaptureOperation:{slot:0,key:'old'},photos,
    syncHostCaptureUI(){},syncPersistenceUI(){},updateCaptureScreenUI(){},transitionSession(){},
    showToast(text){message=text;},captureHostPhoto:async()=>{app.hostCaptureOperation=null;throw Object.assign(new Error('retired'),{code:'capture_superseded'});}};
  await retryHostCapture(app);
  assert.match(message,/Select New Session/);assert.doesNotMatch(message,/Capture Now/);
  assert.equal(app.photos,photos);assert.equal(app.captureBusy,false);
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
