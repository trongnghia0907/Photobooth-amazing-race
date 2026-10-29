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
  container.replaceChildren();
  app.lastUploadedUrl=targetUrl;
  const image=document.createElement('img');
  image.src=share.qr_image_url;
  image.alt='QR mở đúng ảnh Photobooth đã xác nhận';
  image.className='w-32 h-32 object-contain';
  image.onerror=()=>{document.getElementById('qrStatusBadge').textContent='Không tải được ảnh QR — hãy thử lại';};
  container.appendChild(image);
  const input=document.getElementById('qrExternalUrlInput');
  if(input) input.value=targetUrl;
  const open=document.getElementById('qrExternalOpenBtn');
  if(open){open.href=targetUrl;open.removeAttribute('aria-disabled');}
  document.getElementById('qrStatusBadge').textContent='QR sẵn sàng • Ảnh riêng';
  const pill=document.getElementById('qrReadyPill');
  pill.textContent='Đã lưu & tạo link ảnh riêng';
  pill.className='text-emerald-800 text-xs font-bold';
  document.getElementById('qrDescriptionText').textContent='Quét QR để xem/tải đúng ảnh này. Laptop và public URL phải đang hoạt động.';
}
