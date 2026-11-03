import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {renderQRCodeVisual} from '../src/components/qr-view.js';
import {showQRUnavailable} from '../src/components/qr-status.js';

test('Guest markup removes consent, duplicate new session and QR debug controls',()=>{
  const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
  const kiosk=readFileSync(new URL('../src/features/home/kiosk.js',import.meta.url),'utf8');
  assert.doesNotMatch(kiosk,/eventDisplayConsent|Tôi đồng ý/);
  assert.doesNotMatch(html,/Khách tiếp theo|QR Riêng Cho Ảnh Của Bạn|qrExternalUrlInput|qrReadyPill|confirmQRCodeBtn/);
  assert.match(html,/id="newSessionButton"/);assert.match(html,/Your QR code expires in 24 hours\./);
  const persistence=readFileSync(new URL('../src/services/photo-repository.js',import.meta.url),'utf8');
  assert.match(html,/onclick="app.confirmAndSaveSession\(true\)"[^>]*>Confirm, Display Photo &amp; Get QR/);
  assert.match(persistence,/publishToEvent=false/);
  assert.match(persistence,/confirmationStarted\?previousConsent:publishToEvent===true\|\|previousConsent/);
});

test('Ready QR has only image and lifetime; failures show no technical details',()=>{
  const previous=globalThis.document,nodes={};
  for(const id of ['qrCodeContainer','qrExpiryMessage','qrDescriptionText','qrLoadingOverlay'])nodes[id]={dataset:{},classList:{add(){},remove(){}}};
  const container=nodes.qrCodeContainer;container.replaceChildren=()=>{container.image=null;};container.querySelector=()=>container.image;
  container.appendChild=image=>{container.image=image;image.isConnected=true;};
  nodes.compositeCanvas={toDataURL:()=> 'saved'};
  globalThis.document={getElementById:id=>nodes[id],createElement:()=>({})};
  const url='https://photos.test/p/test-token';
  const app={lastSavedImage:'saved',activeShare:{share_url:url,public_ready:true,expires_at:'2027-01-01T00:00:00Z',qr_image_url:'/p/test-token/qr.png'},syncPersistenceUI(){}};
  try{
    renderQRCodeVisual(app,url);container.image.onload();
    assert.equal(container.dataset.phase,'ready');assert.equal(nodes.qrExpiryMessage.hidden,false);assert.equal(nodes.qrDescriptionText.hidden,true);
    showQRUnavailable(app,'PUBLIC_BASE_URL localhost secret debug','error');
    assert.equal(nodes.qrExpiryMessage.hidden,true);assert.equal(nodes.qrDescriptionText.hidden,false);
    assert.doesNotMatch(nodes.qrDescriptionText.textContent,/PUBLIC_BASE_URL|localhost|secret|debug/);
    app.activeShare.expires_at=null;renderQRCodeVisual(app,url);assert.notEqual(container.dataset.phase,'ready');
  }finally{globalThis.document=previous;}
});
