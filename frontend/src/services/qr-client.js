import { request } from './api-client.js';
import { newId } from '../utils/ids.js';
import { showQRUnavailable,renderQRConnectionMode } from '../components/qr-status.js';

function currentShare(app) {
  const canvas=document.getElementById('compositeCanvas');
  return app.activeShare && app.lastSavedImage && canvas?.toDataURL('image/png') === app.lastSavedImage
    && app.activeShare.composite_id === app.finalOperation?.compositeId
    && app.serverSession?.status === 'completed'
    && !app.pendingPhotos.some(Boolean) && !app.pendingDeletion;
}

function confirmedSnapshot(app) {
  const canvas=document.getElementById('compositeCanvas');
  return app.finalOperation?.compositeId && app.serverSession?.status==='completed'
    && app.lastSavedImage && canvas?.toDataURL('image/png')===app.lastSavedImage
    && !app.pendingPhotos.some(Boolean) && !app.pendingDeletion;
}

function showNextStep(app) {
  if (confirmedSnapshot(app)) {
    const missingPublicOrigin=app.shareError?.includes('PUBLIC_BASE_URL');
    const message=missingPublicOrigin?'A public HTTPS address is not configured yet. Your photo is safe; ask event staff to complete setup before creating a QR code.'
      :app.shareError?'Your photo is saved, but the QR code is not ready. The system will retry automatically; please ask event staff if it remains unavailable.'
      :'Your photo is saved. Select “Confirm & Create QR” to try again.';
    showQRUnavailable(app,message,missingPublicOrigin?'configuration_error':'error');
  } else {
    const config=app.sharingConfig;
    const hint=config && !config.configured ? ` ${config.message}` : '';
    showQRUnavailable(app, `Select “Confirm & Create QR” to save your edited composite and create a QR code.${hint}`);
  }
}

export function loadSharingConfig(app, force=false) {
  if (app.sharingConfig && !force) return Promise.resolve(app.sharingConfig);
  if (app.sharingConfigRequest) return app.sharingConfigRequest;
  app.sharingConfigRequest=request('/health').then(health=>{
    if(!health.sharing) throw new Error('The backend is out of date. Stop it and restart with python scripts/run_local_backend.py from the project folder.');
    app.sharingConfig=health.sharing;
    renderQRConnectionMode(app,health.sharing);
    return health.sharing;
  }).catch(error=>{
    app.sharingConfig={configured:false,local_only:false,message:error.message};
    renderQRConnectionMode(app,app.sharingConfig);
    return app.sharingConfig;
  }).finally(()=>{
    app.sharingConfigRequest=null;
  });
  return app.sharingConfigRequest;
}

/** Read-only polling: never saves a composite or creates/rotates a share token. */
export async function refreshPublicQR(app) {
  if(app.currentScreen!=='result'||!confirmedSnapshot(app)||(app.qrRetryFailures||0)>=12
      ||app.publicQRChecking||app.persistenceBusy||app.shareBusy||app.captureBusy)return;
  if(!currentShare(app))return generateQRCodeForCurrentPhoto(app,true,true);
  app.publicQRChecking=true;
  try{
    const configuration=await app.loadSharingConfig(true);
    if(app.currentScreen!=='result'||!currentShare(app))return;
    if(!configuration.configured||configuration.local_only||configuration.lan_only){
      app.qrRetryFailures=(app.qrRetryFailures||0)+1;
      app.activeShare.public_ready=false;
      showQRUnavailable(app,'','configuration_error');return;
    }
    if(['connecting','disconnected'].includes(configuration.tunnel_status)){
      app.activeShare.public_ready=false;app.syncPrintUI?.();
      app.qrRetryFailures=(app.qrRetryFailures||0)+1;
      showQRUnavailable(app,configuration.tunnel_status==='connecting'
        ? 'Connecting to Cloudflare. Your photo is saved; the phone QR will update when HTTPS is ready.'
        : 'The tunnel is disconnected. Your photo is still saved; restart the mobile QR script to get a new HTTPS address.',
      'tunnel_'+configuration.tunnel_status);
      return;
    }
    const context=app.sessionContext,operation=app.finalOperation;
    const share=await request(`/sessions/${context.id}/public-status`,{token:context.token});
    if(app.sessionContext!==context||app.finalOperation!==operation||!currentShare(app))return;
    if(!share){app.activeShare.public_ready=false;showQRUnavailable(app,'This QR code has expired or was revoked.','expired');app.syncPrintUI?.();return;}
    if(share?.composite_id!==operation.compositeId)return;
    if(share.share_url.split('/p/')[1]!==app.activeShare.share_url.split('/p/')[1])throw new Error('Share token changed unexpectedly');
    app.activeShare=share;
    app.qrRetryFailures=0;
    app.renderQRCodeVisual(share.share_url);
    app.syncPrintUI?.();
  }catch(error){
    app.qrRetryFailures=(app.qrRetryFailures||0)+1;
    if(app.activeShare)app.activeShare.public_ready=false;
    if(error.status===404)app.qrRetryFailures=12;
    showQRUnavailable(app,'',error.status===404?'expired':app.qrRetryFailures>=12?'unavailable':'error');
    app.syncPrintUI?.();
  }finally{app.publicQRChecking=false;}
}

export function startPublicQRMonitor(app){
  if(app.publicQRMonitor)return;
  app.publicQRMonitor=setInterval(()=>app.refreshPublicQR().catch(()=>{
    if(app.activeShare)app.activeShare.public_ready=false;app.syncPrintUI?.();
    if(app.currentScreen==='result'&&app.activeShare)showQRUnavailable(app,'Could not reach the backend to verify the QR code. Your photo is still saved.','tunnel_disconnected');
  }),5000);
}

export function scheduleQRCodeUpdate(app) {
  // Editing only updates visibility. It NEVER uploads, finalizes or rotates a token.
  if(app.currentScreen !== 'result') return;
  if(currentShare(app)) app.renderQRCodeVisual(app.activeShare.share_url);
  else showNextStep(app);
}

export function setQRProvider(app) {
  // Preserve the old handler name; external providers cannot be re-enabled.
  app.showToast('The QR code was created by the backend, and your photo is saved on the laptop.', 'info');
}

export async function confirmPhotoAndGenerateQR(app) {
  if (app.persistenceBusy || app.captureBusy || app.shareBusy) return;
  if ((!app.serverSession?.finalized && !app.photos.every(Boolean)) || app.hasPendingWork()) {
    app.showToast('Capture all required photos first. If an error occurs, select Retry Save.', 'info');
    return;
  }
  if (!confirmedSnapshot(app)) return app.confirmAndSaveSession();
  return app.generateQRCodeForCurrentPhoto(true);
}

export async function generateQRCodeForCurrentPhoto(app, forceNotify=false, automatic=false) {
  if(currentShare(app)&&!forceNotify) {
    app.renderQRCodeVisual(app.activeShare.share_url);
    return;
  }
  const operation=app.finalOperation;
  if(!forceNotify || !confirmedSnapshot(app)) {
    showNextStep(app);
    return;
  }
  if(app.shareBusy) return;
  if(!automatic)app.qrRetryFailures=0;
  if(!app.qrStartedAt)app.qrStartedAt=performance.now();
  app.shareBusy=true;
  app.syncPersistenceUI();
  operation.finalizeKey ||= newId();
  document.getElementById('qrLoadingOverlay')?.classList.remove('hidden');
  try {
    const configuration=await app.loadSharingConfig(true);
    if(!configuration.configured) throw new Error(configuration.message);
    const result=await request(`/sessions/${app.sessionContext.id}/finalize`,{
      method:'POST',token:app.sessionContext.token,key:operation.finalizeKey,preferAsync:true,
      body:{composite_id:operation.compositeId},
    });
    let share=result.share;
    const url=share ? new URL(share.share_url) : null;
    const host=url?.hostname.toLowerCase().replace(/\.$/,'');
    const loopback=host==='localhost' || host==='[::1]' || /^127\.(?:\d{1,3}\.){2}\d{1,3}$/.test(host || '');
    const parts=(host||'').split('.').map(Number);
    const lan=parts.length===4&&parts.every(v=>Number.isInteger(v)&&v>=0&&v<=255)&&(parts[0]===10||parts[0]===192&&parts[1]===168||parts[0]===172&&parts[1]>=16&&parts[1]<=31);
    const allowed=url && (loopback ? share.local_only===true && ['http:','https:'].includes(url.protocol) : lan ? share.lan_only===true&&['http:','https:'].includes(url.protocol) : url.protocol==='https:');
    if(!share || share.composite_id!==operation.compositeId || !allowed
        || !share.qr_image_url?.startsWith('/p/')) throw new Error('The backend did not confirm a valid share URL.');
    app.activeShare=share;
    if(share.local_only||share.lan_only||['connecting','disconnected'].includes(configuration.tunnel_status)){
      app.qrRetryFailures=(app.qrRetryFailures||0)+1;
      showQRUnavailable(app,'',configuration.tunnel_status==='connecting'?'tunnel_connecting':
        configuration.tunnel_status==='disconnected'?'tunnel_disconnected':'configuration_error');
      return;
    }
    if(!share.local_only&&!share.lan_only){
      if(app.qrPhase!=='ready')showQRUnavailable(app,'Checking this session’s HTTPS photo page…','processing');
      share=await request(`/sessions/${app.sessionContext.id}/public-status`,{token:app.sessionContext.token});
      app.activeShare=share;
    }
    app.shareError='';
    app.qrRetryFailures=0;
    app.renderQRCodeVisual(share.share_url);
  } catch(error) {
    if(app.activeShare)app.activeShare.public_ready=false;
    app.shareError=error.message;
    const missingPublicOrigin=error.message.includes('PUBLIC_BASE_URL');
    app.qrRetryFailures=(app.qrRetryFailures||0)+1;
    if(/hết hạn|thu hồi/.test(error.message)||error.status===404)app.qrRetryFailures=12;
    showQRUnavailable(app,'',missingPublicOrigin?'configuration_error':app.qrRetryFailures>=12?'unavailable':'error');
  } finally {
    app.shareBusy=false;
    app.syncPersistenceUI();
    if(app.qrPhase!=='loading') document.getElementById('qrLoadingOverlay')?.classList.add('hidden');
  }
}
