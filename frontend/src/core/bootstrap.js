import * as module0 from '../features/home/home.js';
import * as module1 from '../services/camera-client.js';
import * as module2 from '../services/preview-provider.js';
import * as module3 from '../services/mock-camera.js';
import * as module4 from '../services/legacy-camera.js';
import * as module5 from '../features/layout/frame.js';
import * as module6 from '../features/layout/slot-detection.js';
import * as module7 from '../services/qr-client.js';
import * as module8 from '../core/router.js';
import * as module9 from '../features/capture/capture.js';
import * as module10 from '../features/capture/countdown.js';
import * as module11 from '../features/capture/retake.js';
import * as module12 from '../utils/timing.js';
import * as module13 from '../features/result/result.js';
import * as module14 from '../features/editor/compositor.js';
import * as module15 from '../utils/canvas.js';
import * as module16 from '../features/editor/filters.js';
import * as module17 from '../features/editor/stickers.js';
import * as module18 from '../features/editor/canvas-interactions.js';
import * as module19 from '../features/editor/text.js';
import * as module20 from '../components/qr-view.js';
import * as module21 from '../services/print-client.js';
import * as module22 from '../components/modal.js';
import * as module23 from '../components/toast.js';
import { createStore } from './store.js';

export function createApp() {
  const state = createStore();
  const app = {};
  for (const key of Object.keys(state)) {
    Object.defineProperty(app, key, { enumerable: true, get: () => state[key], set: value => { state[key] = value; } });
  }
  const modules = [module0, module1, module2, module3, module4, module5, module6, module7, module8, module9, module10, module11, module12, module13, module14, module15, module16, module17, module18, module19, module20, module21, module22, module23];
  for (const module of modules) {
    for (const [name, fn] of Object.entries(module)) {
      app[name] = (...args) => fn(app, ...args);
    }
  }
  return app;
}
