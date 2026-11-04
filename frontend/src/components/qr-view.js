import { showQRUnavailable } from './qr-status.js';
/** Preserve legacy QR presentation, using only the backend's local QR artifact. */
export function copyQRLink(app) {
  const input=document.getElementById('qrExternalUrlInput');
  if(!input || !app.lastUploadedUrl) return;
  input.select();
  try { document.execCommand('copy'); app.showToast('Private photo link copied.', 'success'); }
  catch { app.showToast('Could not copy automatically.', 'info'); }
}

export function renderQRCodeVisual(app,targetUrl) {
  const container=document.getElementById('qrCodeContainer');
  const share=app.activeShare;
  if(!container || !share || targetUrl!==share.share_url) return;
  if(share.local_only||share.lan_only||!share.public_ready||!share.expires_at){
    showQRUnavailable(app,'Waiting for the gateway to verify the HTTPS photo page. Your photo is safely saved.','processing');return;
  }
  const markReady=image=>{
    if(!image.isConnected || app.activeShare?.share_url!==targetUrl) return;
    if(document.getElementById('compositeCanvas')?.toDataURL('image/png')!==app.lastSavedImage) {
      showQRUnavailable(app,'Your photo has changed. Select “Confirm & Create QR” to save the new version.');
      return;
    }
    app.qrPhase='ready';
    clearTimeout(app.qrImageTimer);app.qrImageTimer=null;
    if(app.qrStartedAt){app.qrDisplayMs=Math.round(performance.now()-app.qrStartedAt);app.qrStartedAt=null;}
    app.shareError='';
    container.dataset.phase='ready';
    app.lastUploadedUrl=targetUrl;
    document.getElementById('qrExpiryMessage').hidden=false;
    document.getElementById('qrDescriptionText').hidden=true;
    document.getElementById('qrLoadingOverlay')?.classList.add('hidden');
    app.syncPersistenceUI();
  };
  const existing=container.querySelector('img');
  if(container.dataset.shareUrl===targetUrl && existing) {
    if(existing.complete && existing.naturalWidth>0) {markReady(existing);return;}
    if(!existing.complete) return;
  }
  container.replaceChildren();
  container.dataset.shareUrl=targetUrl;
  container.dataset.phase='loading';
  app.qrPhase='loading';
  document.getElementById('qrExpiryMessage').hidden=true;
  const description=document.getElementById('qrDescriptionText');description.hidden=false;description.textContent='Preparing your QR code…';
  document.getElementById('qrLoadingOverlay')?.classList.remove('hidden');
  const image=document.createElement('img');
  image.alt='QR code for your confirmed photobooth photo';
  image.className='guest-qr-image';
  image.onload=()=>markReady(image);
  image.onerror=()=>{
    if(!image.isConnected || app.activeShare?.share_url!==targetUrl) return;
    app.shareError='Your photo is saved, but the QR PNG could not be downloaded. Select “Confirm & Create QR” to retry; you do not need to retake the photo.';
    showQRUnavailable(app,app.shareError,'error');
    app.syncPersistenceUI();
  };
  container.appendChild(image);
  clearTimeout(app.qrImageTimer);
  app.qrImageTimer=setTimeout(()=>{
    if(image.isConnected && app.activeShare?.share_url===targetUrl && app.qrPhase==='loading')image.onerror();
  },10000);
  image.src=share.qr_image_url+'?origin='+encodeURIComponent(new URL(targetUrl).origin);
}
