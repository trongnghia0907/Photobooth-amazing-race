/** No fabricated share URL and no third-party requests in default demo. */
export function showQRUnavailable(app, message) {
  clearTimeout(app.qrUpdateDebounceTimer);
  app.qrUpdateDebounceTimer = null;
  app.lastUploadedUrl = '';
  const container = document.getElementById('qrCodeContainer');
  if (container) container.textContent = 'DEMO • QR chưa sẵn sàng';
  const badge = document.getElementById('qrStatusBadge');
  if (badge) badge.textContent = 'DEMO • Chưa có link tải ảnh';
  const pill = document.getElementById('qrReadyPill');
  if (pill) { pill.textContent = 'Chia sẻ: TODO'; pill.className = 'text-amber-800 text-xs font-bold'; }
  const description = document.getElementById('qrDescriptionText');
  if (description) description.textContent = message;
  const input = document.getElementById('qrExternalUrlInput');
  if (input) input.value = '';
  const open = document.getElementById('qrExternalOpenBtn');
  if (open) { open.removeAttribute('href'); open.setAttribute('aria-disabled', 'true'); }
  document.getElementById('qrLoadingOverlay')?.classList.add('hidden');
}
