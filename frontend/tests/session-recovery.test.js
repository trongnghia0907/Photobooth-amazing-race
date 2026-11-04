import test from 'node:test';
import assert from 'node:assert/strict';
import {rememberSession,forgetRememberedSession,restoreSavedSession} from '../src/services/session-recovery.js';

test('reload credential cache contains only the tab session context and New Session removes it',()=>{
  const previous=Object.getOwnPropertyDescriptor(globalThis,'sessionStorage');let cached;
  Object.defineProperty(globalThis,'sessionStorage',{configurable:true,value:{setItem:(key,value)=>{cached=value;},removeItem:()=>{cached=null;}}});
  try{
    const context={id:'session',token:'owner',createKey:'operation',slotCount:4,layout:'landscape_4',request:Promise.resolve(),privatePath:'never-cache'};
    rememberSession(context);assert.deepEqual(Object.keys(JSON.parse(cached)).sort(),['createKey','id','layout','slotCount','token']);
    forgetRememberedSession();assert.equal(cached,null);
  }finally{if(previous)Object.defineProperty(globalThis,'sessionStorage',previous);else delete globalThis.sessionStorage;}
});

test('corrupt recovery data blocks capture instead of silently starting a replacement session',async()=>{
  const previous=Object.getOwnPropertyDescriptor(globalThis,'sessionStorage');let raw='{broken';
  Object.defineProperty(globalThis,'sessionStorage',{configurable:true,value:{getItem:()=>raw}});
  const app={syncPersistenceUI(){},ensureSession(){throw new Error('Must not create a replacement session');}};
  try{
    assert.equal(await restoreSavedSession(app),true);assert.equal(app.resumeRecoveryPending,true);assert.match(app.persistenceError,/Event staff must check/);
    raw=JSON.stringify({token:'a'.repeat(64),createKey:'b'.repeat(32),id:'../../admin',slotCount:4,layout:'landscape_4'});
    assert.equal(await restoreSavedSession(app),true);assert.equal(app.sessionContext,undefined);
  }finally{if(previous)Object.defineProperty(globalThis,'sessionStorage',previous);else delete globalThis.sessionStorage;}
});

test('pending camera recovery keeps its idempotency key, never caches photo bytes or private paths',()=>{
  const previous=Object.getOwnPropertyDescriptor(globalThis,'sessionStorage');let cached;
  Object.defineProperty(globalThis,'sessionStorage',{configurable:true,value:{setItem:(_,value)=>{cached=JSON.parse(value);}}});
  try{
    rememberSession({id:'session',token:'owner',createKey:'operation',slotCount:4,layout:'landscape_4',
      cameraCapture:{slot:2,key:'same-camera-request',completeAfterRecovery:true,retryNewShot:false,photoBytes:'SECRET',privatePath:'PRIVATE'}});
    assert.deepEqual(cached.cameraCapture,{slot:2,key:'same-camera-request',submitted:true,completeAfterRecovery:true,retryNewShot:false});
    assert.ok(!JSON.stringify(cached).includes('SECRET')&&!JSON.stringify(cached).includes('PRIVATE'));
  }finally{if(previous)Object.defineProperty(globalThis,'sessionStorage',previous);else delete globalThis.sessionStorage;}
});

test('invalid pending camera slots or receipts block recovery before any request',async()=>{
  const previous=Object.getOwnPropertyDescriptor(globalThis,'sessionStorage');let pending;
  Object.defineProperty(globalThis,'sessionStorage',{configurable:true,value:{getItem:()=>JSON.stringify({
    token:'a'.repeat(64),createKey:'b'.repeat(32),id:'0'.repeat(8)+'-0000-0000-0000-'+'0'.repeat(12),slotCount:4,layout:'landscape_4',cameraCapture:pending})}});
  try{
    for(pending of [null,false,{}, {slot:4,key:'x'.repeat(32),completeAfterRecovery:true,retryNewShot:false}]){
      const app={syncPersistenceUI(){},ensureSession(){assert.fail('No capture/session request allowed');}};
      assert.equal(await restoreSavedSession(app),true);assert.equal(app.resumeRecoveryPending,true);assert.equal(app.sessionContext,undefined);
    }
  }finally{if(previous)Object.defineProperty(globalThis,'sessionStorage',previous);else delete globalThis.sessionStorage;}
});
