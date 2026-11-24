import test from 'node:test';
import assert from 'node:assert/strict';
import {pollPrintJob,stopPrintPolling,syncPrintUI} from '../src/services/print-client.js';
import {refreshPublicQR} from '../src/services/qr-client.js';

test('HTTPS print preview opens, changes with QR version and reports pending without hiding the original',()=>{
  const previous=globalThis.document,nodes={};
  for(const id of ['printPhotoBtn','printReadyPreview','printReadyBox','printReadyDownload','compositeCanvas','printCopies','printStatus'])nodes[id]={dataset:{},options:[1,2,3],removeAttribute(name){delete this[name];}};
  nodes.compositeCanvas.toDataURL=()=> 'original';nodes.compositeCanvas.parentElement={hidden:false};
  globalThis.document={getElementById:id=>nodes[id]};
  const asset={final_id:'final',print_ready_version:'v1',image_url:'/p/token/image',download_url:'/p/token/download'};
  const app={sharingConfig:{cloud_configured:true},cloudShare:{public_ready:true,composite_id:'composite',print_asset:asset},serverSession:{status:'completed'},finalOperation:{compositeId:'composite'},lastSavedImage:'original',hasPendingWork:()=>false,printConfig:{available:true,max_copies:3}};
  try{
    syncPrintUI(app);
    assert.equal(nodes.compositeCanvas.parentElement.hidden,false);
    assert.equal(nodes.printPhotoBtn.disabled,true);
    nodes.printReadyPreview.onload();
    assert.equal(nodes.printReadyBox.hidden,false);assert.equal(nodes.compositeCanvas.parentElement.hidden,true);assert.equal(nodes.printReadyPreview.src,'/p/token/image?print_ready=1&v=v1');
    assert.equal(nodes.printReadyDownload.href,'/p/token/download?print_ready=1&v=v1');
    asset.print_ready_version='v2';syncPrintUI(app);assert.equal(nodes.printReadyPreview.src,'/p/token/image?print_ready=1&v=v2');
    app.cloudShare.print_asset=null;syncPrintUI(app);
    assert.equal(nodes.printReadyBox.hidden,true);assert.equal(nodes.compositeCanvas.parentElement.hidden,false);assert.equal(nodes.printStatus.textContent,'Preparing the print with QR code.');assert.equal(nodes.printPhotoBtn.disabled,true);
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

test('cloud readiness renders immediately after the ACK without another health or gateway request',async()=>{
  const originalFetch=globalThis.fetch,originalDocument=globalThis.document;
  const requests=[],rendered=[];
  const cloudUrl='https://event.invalid/p/confirmed-token';
  let payload={state:'pending',composite_id:'composite'};
  globalThis.document={getElementById:id=>id==='compositeCanvas'?{toDataURL:()=> 'original'}:null};
  globalThis.fetch=async url=>{requests.push(url);return {ok:true,json:async()=>payload};};
  const app={currentScreen:'result',sharingConfig:{cloud_configured:true},sessionContext:{id:'session',token:'owner'},
    activeShare:{composite_id:'composite',public_ready:true,share_url:'https://gateway.invalid/p/local-token'},
    finalOperation:{compositeId:'composite'},serverSession:{status:'completed'},lastSavedImage:'original',pendingPhotos:[],
    renderQRCodeVisual:url=>rendered.push(url)};
  try{
    await refreshPublicQR(app);
    assert.deepEqual(rendered,[]);
    payload={state:'ready',composite_id:'composite',share_url:cloudUrl};
    await refreshPublicQR(app);
    assert.deepEqual(rendered,[cloudUrl]);
    assert.deepEqual(requests,Array(2).fill('/api/sessions/session/cloud-share'));
  }finally{globalThis.fetch=originalFetch;globalThis.document=originalDocument;}
});
