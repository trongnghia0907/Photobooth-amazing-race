import {defineConfig} from '@playwright/test';
import {randomUUID,randomBytes} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {existsSync} from 'node:fs';
const chrome=process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe';
process.env.AMAZING_RACE_PREVIEW_TEST_PASSWORD ||= randomBytes(24).toString('hex');
const env={OSA_TEST_PORT:'8028',OSA_BACKEND_URL:'http://127.0.0.1:8028',VITE_CAMERA_SOURCE:'host',EVENT_GALLERY_AUTO_PUBLISH:'true',
  OSA_FRONTEND_DIST:fileURLToPath(new URL('./dist-host/',import.meta.url)),BOOTH_PAIRING_KEY:'preview-only-disposable-pairing-key',
  ADMIN_USERNAME:'preview-host',ADMIN_PASSWORD:process.env.AMAZING_RACE_PREVIEW_TEST_PASSWORD,PUBLIC_BASE_URL:'https://photos.test',
  GUEST_SESSION_IDLE_SECONDS:'0',OSA_STORAGE_ROOT:fileURLToPath(new URL('../.tools/preview-'+randomUUID()+'/',import.meta.url))};
export default defineConfig({testDir:'./tests/preview',workers:1,timeout:120000,expect:{timeout:12000},
  outputDir:'test-results/preview',use:{baseURL:'http://127.0.0.1:5188',viewport:{width:1180,height:820},headless:true,launchOptions:existsSync(chrome)?{executablePath:chrome}:{}},
  webServer:[{command:'node tests/backend-server.js',url:'http://127.0.0.1:8028/api/health',env,reuseExistingServer:false},
    {command:'npm run dev -- --host 127.0.0.1 --port 5188',url:'http://127.0.0.1:5188',env,reuseExistingServer:false}]});
