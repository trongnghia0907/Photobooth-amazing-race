import test from 'node:test';
import assert from 'node:assert/strict';
import {pollPrintJob,stopPrintPolling,syncPrintUI} from '../src/services/print-client.js';

test('HTTPS print preview opens, changes with QR version and reports pending without hiding the original',()=>{
  const previous=globalThis.document,nodes={};
  for(const id of ['printPhotoBtn','printReadyPreview','printReadyBox','printReadyDownload','compositeCanvas','printCopies','printStatus'])nodes[id]={dataset:{},options:[1,2,3],removeAttribute(name){delete this[name];}};
  nodes.compositeCanvas.toDataURL=()=> 'original';nodes.compositeCanvas.parentElement={hidden:false};
  globalThis.document={getElementById:id=>nodes[id]};
  const app={activeShare:{public_ready:true,print_ready:{},final_id:'final',composite_id:'composite',print_ready_version:'v1',image_url:'/p/token/image',download_url:'/p/token/download'},serverSession:{status:'completed'},finalOperation:{compositeId:'composite'},lastSavedImage:'original',hasPendingWork:()=>false,printConfig:{available:true,max_copies:3}};
  try{
    syncPrintUI(app);assert.equal(nodes.printReadyBox.open,true);assert.equal(nodes.compositeCanvas.parentElement.hidden,true);assert.equal(nodes.printReadyPreview.src,'/p/token/image?v=v1');
    app.activeShare.print_ready_version='v2';syncPrintUI(app);assert.equal(nodes.printReadyPreview.src,'/p/token/image?v=v2');
    app.activeShare.print_ready=null;app.activeShare.print_ready_error='Chờ HTTPS';syncPrintUI(app);
    assert.equal(nodes.printReadyBox.hidden,true);assert.equal(nodes.compositeCanvas.parentElement.hidden,false);assert.equal(nodes.printStatus.textContent,'Chờ HTTPS');assert.equal(nodes.printPhotoBtn.disabled,true);
  }finally{globalThis.document=previous;}
});

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
