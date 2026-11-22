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
if (defaults.demoEnabled || defaults.hostCameraEnabled) {
  if ((await initializeBoothAccess()) !== false && await loadEventConfiguration(app)) {
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
