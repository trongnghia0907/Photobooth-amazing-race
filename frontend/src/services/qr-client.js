import { request } from './api-client.js';
import { newId } from '../utils/ids.js';
import { showQRUnavailable } from '../components/qr-status.js';

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
    showQRUnavailable(app, app.shareError || 'Ảnh đã lưu. Bấm “Xác nhận & Tạo QR” để thử tạo QR lại.',
      app.shareError?.includes('PUBLIC_BASE_URL') ? 'configuration_error' : 'error');
  } else {
    const config=app.sharingConfig;
    const hint=config && !config.configured ? ` ${config.message}` : '';
    showQRUnavailable(app, `Bấm “Xác nhận & Tạo QR” để lưu bản ảnh ghép đang chỉnh và tạo QR tự động.${hint}`);
  }
}

export function loadSharingConfig(app, force=false) {
  if (app.sharingConfig && !force) return Promise.resolve(app.sharingConfig);
  if (app.sharingConfigRequest) return app.sharingConfigRequest;
  app.sharingConfigRequest=request('/health').then(health=>{
    if(!health.sharing) throw new Error('Backend đang chạy bản cũ. Hãy dừng và khởi động lại backend bằng python scripts/run_local_backend.py từ thư mục dự án.');
    app.sharingConfig=health.sharing;
    return health.sharing;
  }).catch(error=>{
    app.sharingConfig={configured:false,local_only:false,message:error.message};
    return app.sharingConfig;
  }).finally(()=>{
    app.sharingConfigRequest=null;
    if(app.currentScreen==='result' && !app.persistenceBusy && !app.shareBusy) app.generateQRCodeForCurrentPhoto(false);
  });
  return app.sharingConfigRequest;
}

export function scheduleQRCodeUpdate(app) {
  // Editing only updates visibility. It NEVER uploads, finalizes or rotates a token.
  if(app.currentScreen !== 'result') return;
  if(currentShare(app)) app.renderQRCodeVisual(app.activeShare.share_url);
  else showNextStep(app);
}

export function setQRProvider(app) {
  // Preserve the old handler name; external providers cannot be re-enabled.
  app.showToast('QR được tạo nội bộ từ backend và ảnh lưu trên laptop.', 'info');
}

export async function confirmPhotoAndGenerateQR(app) {
  if (app.persistenceBusy || app.captureBusy || app.shareBusy) return;
  if ((!app.serverSession?.finalized && !app.photos.every(Boolean)) || app.hasPendingWork()) {
    app.showToast('Cần lưu đủ ảnh chụp trước. Nếu có lỗi, bấm Thử lưu lại.', 'info');
    return;
  }
  if (!confirmedSnapshot(app)) return app.confirmAndSaveSession();
  return app.generateQRCodeForCurrentPhoto(true);
}

export async function generateQRCodeForCurrentPhoto(app, forceNotify=false) {
  if(currentShare(app)) {
    app.renderQRCodeVisual(app.activeShare.share_url);
    return;
  }
  const operation=app.finalOperation;
  if(!forceNotify || !confirmedSnapshot(app)) {
    showNextStep(app);
    return;
  }
  if(app.shareBusy) return;
  app.shareBusy=true;
  app.syncPersistenceUI();
  operation.finalizeKey ||= newId();
  document.getElementById('qrLoadingOverlay')?.classList.remove('hidden');
  try {
    const configuration=await app.loadSharingConfig(true);
    if(!configuration.configured) throw new Error(configuration.message);
    const result=await request(`/sessions/${app.sessionContext.id}/finalize`,{
      method:'POST',token:app.sessionContext.token,key:operation.finalizeKey,
      body:{composite_id:operation.compositeId},
    });
    const share=result.share;
    const url=share ? new URL(share.share_url) : null;
    const host=url?.hostname.toLowerCase().replace(/\.$/,'');
    const loopback=host==='localhost' || host==='[::1]' || /^127\.(?:\d{1,3}\.){2}\d{1,3}$/.test(host || '');
    const parts=(host||'').split('.').map(Number);
    const lan=parts.length===4&&parts.every(v=>Number.isInteger(v)&&v>=0&&v<=255)&&(parts[0]===10||parts[0]===192&&parts[1]===168||parts[0]===172&&parts[1]>=16&&parts[1]<=31);
    const allowed=url && (loopback ? share.local_only===true && ['http:','https:'].includes(url.protocol) : lan ? share.lan_only===true&&['http:','https:'].includes(url.protocol) : url.protocol==='https:');
    if(!share || share.composite_id!==operation.compositeId || !allowed
        || !share.qr_image_url?.startsWith('/p/')) throw new Error('Backend chưa xác nhận share URL hợp lệ.');
    app.activeShare=share;
    app.shareError='';
    app.renderQRCodeVisual(share.share_url);
  } catch(error) {
    app.shareError=error.message;
    showQRUnavailable(app,`Ảnh đã lưu. ${error.message}`,error.message.includes('PUBLIC_BASE_URL') ? 'configuration_error' : 'error');
  } finally {
    app.shareBusy=false;
    app.syncPersistenceUI();
    if(app.qrPhase!=='loading') document.getElementById('qrLoadingOverlay')?.classList.add('hidden');
  }
}
