/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function copyQRLink(app) {
  const input = document.getElementById('qrExternalUrlInput');
  if (!input || !app.lastUploadedUrl) return;
  input.select();
  try {
    document.execCommand('copy');
    app.showToast('Đã sao chép đường dẫn trang Web tải ảnh!', 'success');
  } catch (e) {
    app.showToast('Không thể sao chép tự động.', 'info');
  }
}

export function renderQRCodeVisual(app, targetUrl) {
  const qrContainer = document.getElementById('qrCodeContainer');
  const urlInput = document.getElementById('qrExternalUrlInput');
  const openBtn = document.getElementById('qrExternalOpenBtn');
  if (!qrContainer) return;

  qrContainer.innerHTML = '';
  app.lastUploadedUrl = targetUrl;

  if (urlInput) urlInput.value = targetUrl;
  if (openBtn) openBtn.href = targetUrl;

  try {
    if (typeof QRCode !== 'undefined') {
      new QRCode(qrContainer, {
        text: targetUrl,
        width: 132,
        height: 132,
        colorDark: '#1E40AF',
        colorLight: '#FFFFFF',
        correctLevel: QRCode.CorrectLevel.M
      });
    } else {
      throw new Error('QRCode library not loaded');
    }
  } catch (e) {
    const qrImg = document.createElement('img');
    qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=150x150&color=1E40AF&bgcolor=FFFFFF&data=${encodeURIComponent(targetUrl)}`;
    qrImg.className = 'w-32 h-32 object-contain';
    qrContainer.appendChild(qrImg);
  }
}
