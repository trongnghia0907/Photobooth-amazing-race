import { defaults } from '../config/defaults.js';
import { generateLegacyQRCodeForCurrentPhoto } from './legacy-qr.js';
import { showQRUnavailable } from '../components/qr-status.js';

/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function scheduleQRCodeUpdate(app) {
  if (app.currentScreen !== 'result') return;
  if (!defaults.enableLegacyUpload) {
    showQRUnavailable(app, 'DEMO: QR chia sẻ chưa triển khai. Dùng Tải ảnh về.');
    return;
  }
  if (app.qrUpdateDebounceTimer) clearTimeout(app.qrUpdateDebounceTimer);
  const badge = document.getElementById('qrStatusBadge');
  if (badge) badge.textContent = '✏️ Đang chờ cập nhật QR...';

  app.qrUpdateDebounceTimer = setTimeout(() => {
    app.generateQRCodeForCurrentPhoto(false);
  }, 1400);
}

export function setQRProvider(app, provider) {
  app.qrCloudProvider = provider;
  app.generateQRCodeForCurrentPhoto(true);
}

export async function generateQRCodeForCurrentPhoto(app, forceNotify = false) {
  if (!defaults.enableLegacyUpload) {
    showQRUnavailable(app, 'DEMO: QR chia sẻ chưa triển khai. Dùng Tải ảnh về.');
    if (forceNotify) app.showToast('DEMO: Không upload ảnh. QR riêng sẽ có ở phase sau.', 'info');
    return;
  }
  return generateLegacyQRCodeForCurrentPhoto(app, forceNotify);
}
