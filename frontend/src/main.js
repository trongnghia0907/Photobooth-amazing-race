import './styles/base.css';
import './styles/components.css';
import './styles/print.css';
import './styles/camera.css';
import './styles/kiosk.css';
import { createApp } from './core/bootstrap.js';
import { bindEvents } from './core/events.js';
import { defaults } from './config/defaults.js';
import { initializeBoothAccess } from './services/booth-access.js';
import { loadEventConfiguration } from './services/event-config.js';

const app = createApp();
bindEvents(app);
app.initializeKioskUI();
const badge = document.createElement('div');
badge.id = 'demoModeBadge';
badge.className = 'bg-amber-100 text-amber-800 text-center text-xs font-bold p-2';
badge.textContent = defaults.demoEnabled
  ? 'DEMO • Photos are saved, private QR codes and print queue use the backend • No physical camera shutter'
  : 'Production is not supported yet: physical camera and printing are not integrated; demo capture is disabled.';
document.body.insertBefore(badge, document.querySelector('header'));
if (defaults.demoEnabled || defaults.hostCameraEnabled) {
  await initializeBoothAccess();
  if(await loadEventConfiguration(app)){
  await app.restoreSavedSession();
  await app.refreshRecentGallery();
  app.loadSharingConfig();
  app.startPublicQRMonitor();
  app.loadPrintConfig();
  app.init().catch(error => {
    console.error(error);
    app.showToast(error.message, 'error');
  });
  }
}
