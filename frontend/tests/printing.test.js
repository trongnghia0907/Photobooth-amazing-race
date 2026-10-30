import test from 'node:test';
import assert from 'node:assert/strict';
import {pollPrintJob,stopPrintPolling} from '../src/services/print-client.js';

test('leaving the page while a print status request is in flight never restarts polling',async()=>{
  const originalFetch=globalThis.fetch;
  let finish;
  globalThis.fetch=()=>new Promise(resolve=>{finish=resolve;});
  const app={printOperation:{sid:'session',token:'owner',job:{id:'job'}},printPollTimer:null,
    printPollingStopped:false,syncPrintUI(){throw new Error('Detached page must not update');}};
  try{
    const pending=pollPrintJob(app);
    stopPrintPolling(app);
    finish({ok:true,json:async()=>({id:'job',status:'processing'})});
    await pending;
    assert.equal(app.printPollTimer,null);
    assert.equal(app.printPollingStopped,true);
  }finally{globalThis.fetch=originalFetch;}
});
