import { showQRUnavailable } from './qr-status.js';
/** Preserve legacy QR presentation, using only the backend's local QR artifact. */
export function copyQRLink(app) {
  const input=document.getElementById('qrExternalUrlInput');
  if(!input || !app.lastUploadedUrl) return;
  input.select();
  try { document.execCommand('copy'); app.showToast('Đã sao chép link ảnh riêng.', 'success'); }
  catch { app.showToast('Không thể sao chép tự động.', 'info'); }
}

export function renderQRCodeVisual(app,targetUrl) {
  const container=document.getElementById('qrCodeContainer');
  const share=app.activeShare;
  if(!container || !share || targetUrl!==share.share_url) return;
  const markReady=image=>{
    if(!image.isConnected || app.activeShare?.share_url!==targetUrl) return;
    if(document.getElementById('compositeCanvas')?.toDataURL('image/png')!==app.lastSavedImage) {
      showQRUnavailable(app,'Ảnh đã thay đổi. Bấm “Xác nhận & Tạo QR” để lưu bản mới.');
      return;
    }
    app.qrPhase='ready';
    app.shareError='';
    container.dataset.phase='ready';
    app.lastUploadedUrl=targetUrl;
    const input=document.getElementById('qrExternalUrlInput');
    if(input) input.value=targetUrl;
    const open=document.getElementById('qrExternalOpenBtn');
    if(open){open.href=targetUrl;open.removeAttribute('aria-disabled');}
    document.getElementById('qrStatusBadge').textContent=share.local_only ? 'QR sẵn sàng • Chỉ trên máy này' : 'QR sẵn sàng • Ảnh riêng';
    const pill=document.getElementById('qrReadyPill');
    pill.textContent=share.local_only ? 'Chế độ kiểm thử localhost' : 'Đã lưu & tạo link ảnh riêng';
    pill.className=share.local_only ? 'text-amber-800 text-xs font-bold' : 'text-emerald-800 text-xs font-bold';
    document.getElementById('qrDescriptionText').textContent=share.local_only
      ? 'Ảnh đã lưu. Bấm Mở Web để kiểm tra Guest Photo Page và tải ảnh ngay trên máy này.'
      : 'Quét QR để xem/tải đúng ảnh này. Laptop và public URL phải đang hoạt động.';
    const warning=document.getElementById('qrLocalWarning');
    if(warning) warning.hidden=!share.local_only;
    const lanWarning=document.getElementById('qrLanWarning');if(lanWarning)lanWarning.hidden=!share.lan_only;
    if(share.lan_only){
      document.getElementById('qrStatusBadge').textContent='QR sẵn sàng • Cùng Wi-Fi';
      document.getElementById('qrReadyPill').textContent='Chế độ kiểm thử LAN';
      document.getElementById('qrDescriptionText').textContent='Quét QR khi điện thoại ở cùng Wi-Fi với laptop. Không dùng qua 4G/5G.';
    }
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
  document.getElementById('qrStatusBadge').textContent='Ảnh đã lưu • Đang tải QR…';
  document.getElementById('qrLoadingOverlay')?.classList.remove('hidden');
  const image=document.createElement('img');
  image.alt='QR mở đúng ảnh Photobooth đã xác nhận';
  image.className='w-32 h-32 object-contain';
  image.onload=()=>markReady(image);
  image.onerror=()=>{
    if(!image.isConnected || app.activeShare?.share_url!==targetUrl) return;
    app.shareError='Ảnh đã lưu nhưng không tải được file PNG QR. Bấm “Xác nhận & Tạo QR” để thử lại; không cần chụp lại.';
    showQRUnavailable(app,app.shareError,'error');
    app.syncPersistenceUI();
  };
  container.appendChild(image);
  image.src=share.qr_image_url;
}
