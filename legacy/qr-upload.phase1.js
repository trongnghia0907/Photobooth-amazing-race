/** @deprecated Third-party upload retained only for explicit dev comparison. */
import { showQRUnavailable } from '../components/qr-status.js';

export async function generateLegacyQRCodeForCurrentPhoto(app, forceNotify = false) {
  const qrContainer = document.getElementById('qrCodeContainer');
  const qrBadge = document.getElementById('qrStatusBadge');
  const loadingOverlay = document.getElementById('qrLoadingOverlay');
  const readyPill = document.getElementById('qrReadyPill');
  if (!qrContainer) return;

  if (app.qrUpdateDebounceTimer) {
    clearTimeout(app.qrUpdateDebounceTimer);
    app.qrUpdateDebounceTimer = null;
  }

  const canvas = document.getElementById('compositeCanvas');
  if (!canvas) return;

  if (loadingOverlay) loadingOverlay.classList.remove('hidden');
  if (qrBadge) qrBadge.textContent = '⏳ Đang tải lên Web...';
  if (readyPill) {
    readyPill.className = 'inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-100 text-amber-800 text-xs font-extrabold';
    readyPill.innerHTML = '<span>⏳ Đang đồng bộ ảnh lên Cloud...</span>';
  }

  const fileStamp = Date.now().toString().slice(-6);
  const fileName = `osa-booth-${fileStamp}.jpg`;

  try {
    const imageBlob = await app.canvasToBlob(canvas, 'image/jpeg', 0.92);

    if (app.imgbbApiKey && app.imgbbApiKey.trim().length > 8) {
      try {
        const base64Data = canvas.toDataURL('image/jpeg', 0.90).split(',')[1];
        const formData = new FormData();
        formData.append('image', base64Data);
        const res = await fetch(`https://api.imgbb.com/1/upload?expiration=86400&key=${encodeURIComponent(app.imgbbApiKey.trim())}`, {
          method: 'POST',
          body: formData
        });
        const json = await res.json();
        if (json && json.data && (json.data.url || json.data.url_viewer)) {
          const targetUrl = json.data.url || json.data.url_viewer;
          app.renderQRCodeVisual(targetUrl);
          if (loadingOverlay) loadingOverlay.classList.add('hidden');
          if (qrBadge) qrBadge.textContent = '✅ Quét tải ảnh';
          if (readyPill) {
            readyPill.className = 'inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-extrabold';
            readyPill.innerHTML = '<span>✅ Đã tạo Web QR</span>';
          }
          if (forceNotify) app.showToast('Đã tạo mã QR liên kết thành công!', 'success');
          return;
        }
      } catch (imgbbErr) {}
    }

    if (app.qrCloudProvider === 'tmpfiles_direct' || app.qrCloudProvider === 'tmpfiles_page') {
      try {
        const formData = new FormData();
        formData.append('file', imageBlob, fileName);
        const response = await fetch('https://tmpfiles.org/api/v1/upload', {
          method: 'POST',
          body: formData
        });
        const result = await response.json();
        if (result && result.status === 'success' && result.data && result.data.url) {
          let rawUrl = result.data.url.replace(/^http:\/\//i, 'https://');
          let finalWebUrl = rawUrl;
          if (app.qrCloudProvider === 'tmpfiles_direct') {
            finalWebUrl = rawUrl.replace('https://tmpfiles.org/', 'https://tmpfiles.org/dl/');
          }
          app.renderQRCodeVisual(finalWebUrl);
          if (loadingOverlay) loadingOverlay.classList.add('hidden');
          if (qrBadge) qrBadge.textContent = '✅ Quét tải ảnh ngay';
          if (readyPill) {
            readyPill.className = 'inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-extrabold';
            readyPill.innerHTML = '<span>🌐 Đã liên kết Web QR Tải Ảnh</span>';
          }
          if (forceNotify) app.showToast('Đã cập nhật mã QR thành công!', 'success');
          return;
        }
      } catch (tmpErr) {}
    }

    try {
      const formData = new FormData();
      formData.append('file', imageBlob, fileName);
      const response = await fetch('https://file.io/?expires=1d', {
        method: 'POST',
        body: formData
      });
      const result = await response.json();
      if (result && result.success && result.link) {
        app.renderQRCodeVisual(result.link);
        if (loadingOverlay) loadingOverlay.classList.add('hidden');
        if (qrBadge) qrBadge.textContent = '✅ Quét mở Web tải file';
        if (readyPill) {
          readyPill.className = 'inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-extrabold';
          readyPill.innerHTML = '<span>🌐 Đã liên kết Web File.io</span>';
        }
        if (forceNotify) app.showToast('Đã tạo mã QR File.io thành công!', 'success');
        return;
      }
    } catch (fileIoErr) {}

    throw new Error('All cloud gateways unreachable');
  } catch (err) {
    showQRUnavailable(app, 'Không thể upload ảnh. QR chưa sẵn sàng.');
  }
}
