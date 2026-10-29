import './styles/base.css';
import './styles/components.css';
import './styles/print.css';
import { createApp } from './core/bootstrap.js';
import { bindEvents } from './core/events.js';
import { defaults } from './config/defaults.js';

const app = createApp();
bindEvents(app);
for (const id of ['qrProviderSelect', 'imgbbApiKeyInput']) {
  document.getElementById(id).disabled = !defaults.enableLegacyUpload;
}
const badge = document.createElement('div');
badge.id = 'demoModeBadge';
badge.className = 'bg-amber-100 text-amber-800 text-center text-xs font-bold p-2';
badge.textContent = defaults.demoEnabled
  ? 'DEMO • Backend lưu ảnh trên laptop • Chưa có camera shutter thật / QR public / print queue'
  : 'Chưa hỗ trợ production: camera thật, lưu trữ và QR đang chờ triển khai.';
document.body.insertBefore(badge, document.querySelector('header'));
if (defaults.demoEnabled) {
  app.init().catch(error => {
    console.error(error);
    app.showToast(error.message, 'error');
  });
}
