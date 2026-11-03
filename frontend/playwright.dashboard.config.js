import {defineConfig} from '@playwright/test';
import {randomBytes,randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {existsSync} from 'node:fs';

process.env.OSA_TEST_ADMIN_PASSWORD ||= randomBytes(24).toString('hex');
const chrome=process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe';
export default defineConfig({
  testDir:'./tests/dashboard',workers:1,timeout:90000,expect:{timeout:15000},
  outputDir:'test-results/dashboard',
  use:{baseURL:'http://127.0.0.1:8027',viewport:{width:1366,height:900},headless:true,
    launchOptions:existsSync(chrome)?{executablePath:chrome}:{}},
  webServer:{command:'node tests/backend-server.js',url:'http://127.0.0.1:8027/api/health',reuseExistingServer:false,
    env:{OSA_TEST_PORT:'8027',ADMIN_USERNAME:'test-host',ADMIN_PASSWORD:process.env.OSA_TEST_ADMIN_PASSWORD,
      PUBLIC_BASE_URL:'http://localhost:8027',MIN_FREE_SPACE_MB:'0',
      OSA_STORAGE_ROOT:fileURLToPath(new URL('../.tools/dashboard-'+randomUUID()+'/',import.meta.url))}},
});
