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
