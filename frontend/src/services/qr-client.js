import { request } from './api-client.js';
import { showQRUnavailable } from '../components/qr-status.js';

function currentShare(app) {
  const canvas=document.getElementById('compositeCanvas');
  return app.activeShare && app.lastSavedImage && canvas?.toDataURL('image/png') === app.lastSavedImage
    && app.activeShare.composite_id === app.finalOperation?.compositeId
    && app.serverSession?.status === 'completed'
    && !app.pendingPhotos.some(Boolean) && !app.pendingDeletion;
}

export function scheduleQRCodeUpdate(app) {
  // Editing only updates visibility. It NEVER uploads, finalizes or rotates a token.
  if(app.currentScreen !== 'result') return;
  if(currentShare(app)) app.renderQRCodeVisual(app.activeShare.share_url);
  else showQRUnavailable(app,'Hãy xác nhận bản chỉnh sửa cuối cùng để tạo QR riêng.');
}

export function setQRProvider(app) {
  // Preserve the old handler name; external providers cannot be re-enabled.
  app.showToast('QR được tạo nội bộ từ backend và ảnh lưu trên laptop.', 'info');
}

export async function generateQRCodeForCurrentPhoto(app, forceNotify=false) {
  if(currentShare(app)) {
    app.renderQRCodeVisual(app.activeShare.share_url);
    return;
  }
  const canvas=document.getElementById('compositeCanvas');
  const operation=app.finalOperation;
  if(!forceNotify || !operation?.compositeId || app.serverSession?.status!=='completed'
      || !app.lastSavedImage || canvas?.toDataURL('image/png')!==app.lastSavedImage) {
    showQRUnavailable(app,'Xác nhận và lưu composite trước khi tạo QR riêng.');
    return;
  }
  if(app.shareBusy) return;
  app.shareBusy=true;
  operation.finalizeKey ||= crypto.randomUUID();
  document.getElementById('qrLoadingOverlay')?.classList.remove('hidden');
  try {
    const result=await request(`/sessions/${app.sessionContext.id}/finalize`,{
      method:'POST',token:app.sessionContext.token,key:operation.finalizeKey,
      body:{composite_id:operation.compositeId},
    });
    const share=result.share;
    if(!share || share.composite_id!==operation.compositeId || new URL(share.share_url).protocol!=='https:'
        || !share.qr_image_url?.startsWith('/p/')) throw new Error('Backend chưa xác nhận share URL hợp lệ.');
    app.activeShare=share;
    app.shareError='';
    app.renderQRCodeVisual(share.share_url);
  } catch(error) {
    app.shareError=error.message;
    showQRUnavailable(app,`Ảnh đã lưu. ${error.message}`);
  } finally {
    app.shareBusy=false;
    document.getElementById('qrLoadingOverlay')?.classList.add('hidden');
  }
}
