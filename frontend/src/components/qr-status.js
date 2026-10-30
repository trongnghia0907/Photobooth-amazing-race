/** No fabricated share URL and no third-party requests in default demo. */
export function showQRUnavailable(app, message, phase='unconfirmed') {
  app.qrPhase=phase;
  clearTimeout(app.qrUpdateDebounceTimer);
  app.qrUpdateDebounceTimer = null;
  app.lastUploadedUrl = '';
  const container = document.getElementById('qrCodeContainer');
  if (container) {
    container.dataset.phase=phase;
    container.textContent = phase==='unconfirmed' ? 'Chưa xác nhận ảnh' : 'Chưa tạo được QR';
  }
  const badge = document.getElementById('qrStatusBadge');
  if (badge) badge.textContent = phase==='unconfirmed' ? 'DEMO • Bước 1: xác nhận ảnh' : 'Ảnh đã lưu • QR cần xử lý';
  const pill = document.getElementById('qrReadyPill');
  if (pill) { pill.textContent = phase==='unconfirmed' ? 'Chờ xác nhận ảnh' : phase==='configuration_error' ? 'Thiếu hoặc sai cấu hình URL' : 'Lỗi tạo/tải QR'; pill.className = 'text-amber-800 text-xs font-bold'; }
  const description = document.getElementById('qrDescriptionText');
  if (description) description.textContent = message;
  const input = document.getElementById('qrExternalUrlInput');
  if (input) input.value = '';
  const open = document.getElementById('qrExternalOpenBtn');
  if (open) { open.removeAttribute('href'); open.setAttribute('aria-disabled', 'true'); }
  const warning=document.getElementById('qrLocalWarning');
  if(warning) warning.hidden=!app.sharingConfig?.local_only;
  const lanWarning=document.getElementById('qrLanWarning');if(lanWarning)lanWarning.hidden=!app.sharingConfig?.lan_only;
  document.getElementById('qrLoadingOverlay')?.classList.add('hidden');
}
