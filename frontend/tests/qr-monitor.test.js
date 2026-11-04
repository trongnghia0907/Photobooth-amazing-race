import test from 'node:test';
import assert from 'node:assert/strict';
import {refreshPublicQR} from '../src/services/qr-client.js';
import {renderQRConnectionMode} from '../src/components/qr-status.js';

test('public origin polling refreshes an existing share with GET only and preserves token',async()=>{
  const previous={document:globalThis.document,fetch:globalThis.fetch};
  const urls=[],token='a'.repeat(43);
  globalThis.document={getElementById:()=>({toDataURL:()=> 'saved'})};
  globalThis.fetch=async(url,options)=>{
    urls.push([url,options?.method]);
    const share={composite_id:'composite',share_url:`https://new-test.trycloudflare.com/p/${token}`,qr_image_url:`/p/${token}/qr.png`,public_ready:url.endsWith('/public-status')};
    return {ok:true,json:async()=>url.endsWith('/public-status')?share:{share}};
  };
  let rendered;
  const app={currentScreen:'result',lastSavedImage:'saved',serverSession:{status:'completed'},
    activeShare:{composite_id:'composite',share_url:`http://localhost:8000/p/${token}`},
    finalOperation:{compositeId:'composite'},sessionContext:{id:'session',token:'owner'},pendingPhotos:[],
    loadSharingConfig:async()=>({configured:true,tunnel_status:'ready'}),renderQRCodeVisual:url=>{rendered=url;}};
  try{
    await refreshPublicQR(app);
    assert.equal(rendered,`https://new-test.trycloudflare.com/p/${token}`);
    assert.deepEqual(urls,[['/api/sessions/session/public-status','GET']]);
    assert.equal(app.publicQRChecking,false);
    app.shareBusy=true;await refreshPublicQR(app);assert.equal(urls.length,1);
  }finally{globalThis.document=previous.document;globalThis.fetch=previous.fetch;}
});

test('QR mode is a truthful status indicator and exposes no network control',()=>{
  const previous=globalThis.document;const element={dataset:{}};
  globalThis.document={getElementById:id=>id==='qrConnectionMode'?element:null};
  try{
    renderQRConnectionMode({}, {configured:true,local_only:true,tunnel_status:'not_managed'});
    assert.equal(element.textContent,'Local QR • this laptop only');
    renderQRConnectionMode({}, {configured:true,tunnel_status:'connecting'});
    assert.equal(element.textContent,'Connecting to Cloudflare');
    renderQRConnectionMode({}, {configured:true,temporary:true,tunnel_status:'ready'});
    assert.equal(element.textContent,'Cloudflare HTTPS • checking');
    renderQRConnectionMode({}, {configured:true,temporary:true,tunnel_status:'ready',public_origin_verified:true});
    assert.equal(element.textContent,'Cloudflare HTTPS • verified');
    renderQRConnectionMode({}, {configured:false});
    assert.equal(element.textContent,'QR connection not verified');
  }finally{globalThis.document=previous;}
});

test('monitor stops requests outside Review and after twelve consecutive failures',async()=>{
  const previous=globalThis.document;
  globalThis.document={getElementById:()=>({toDataURL:()=> 'saved',dataset:{},classList:{add(){}}})};
  let checks=0;
  const app={currentScreen:'home',lastSavedImage:'saved',serverSession:{status:'completed'},
    activeShare:{composite_id:'composite'},finalOperation:{compositeId:'composite'},pendingPhotos:[],
    loadSharingConfig:async()=>{checks++;return {configured:true,local_only:true};}};
  try{
    await refreshPublicQR(app);assert.equal(checks,0);
    app.currentScreen='result';
    for(let n=0;n<20;n++)await refreshPublicQR(app);
    assert.equal(checks,12);assert.equal(app.activeShare.public_ready,false);
  }finally{globalThis.document=previous;}
});
