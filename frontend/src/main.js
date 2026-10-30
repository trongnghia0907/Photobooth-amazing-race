import './styles/base.css';
import './styles/components.css';
import './styles/print.css';
import './styles/camera.css';
import './styles/kiosk.css';
import { createApp } from './core/bootstrap.js';
import { bindEvents } from './core/events.js';
import { defaults } from './config/defaults.js';
import { initializeBoothAccess } from './services/booth-access.js';

const app = createApp();
bindEvents(app);
app.initializeKioskUI();
for (const id of ['qrProviderSelect', 'imgbbApiKeyInput']) {
  document.getElementById(id).disabled = true;
}
const badge = document.createElement('div');
badge.id = 'demoModeBadge';
badge.className = 'bg-amber-100 text-amber-800 text-center text-xs font-bold p-2';
badge.textContent = defaults.demoEnabled
  ? 'DEMO • Lưu ảnh, QR riêng & hàng đợi in qua backend • Chưa có camera shutter thật'
  : 'Chưa hỗ trợ production: camera thật/in thật chưa tích hợp; demo capture bị tắt.';
document.body.insertBefore(badge, document.querySelector('header'));
if (defaults.demoEnabled || defaults.hostCameraEnabled) {
  await initializeBoothAccess();
  app.loadSharingConfig();
  app.loadPrintConfig();
  app.init().catch(error => {
    console.error(error);
    app.showToast(error.message, 'error');
  });
}
