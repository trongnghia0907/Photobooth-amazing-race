import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';

process.env.OSA_TEST_ADMIN_PASSWORD ||= randomBytes(24).toString('hex');

const backendEnv = {
  ADMIN_USERNAME: 'test-host', ADMIN_PASSWORD: process.env.OSA_TEST_ADMIN_PASSWORD,
  PRINTER_MODE:'mock', ENABLE_PHYSICAL_PRINTING:'false', APP_ENV:'development',
  PUBLIC_BASE_URL: 'https://photos.osa.test', // synthetic test origin; never a deployed public URL
  OSA_BACKEND_URL: 'http://127.0.0.1:8001',
  OSA_STORAGE_ROOT: fileURLToPath(new URL('../.tools/e2e-backend/', import.meta.url)),
};

export default defineConfig({
  testDir: './tests/e2e',
  workers: 1,
  timeout: 90000,
  use: { headless: true, viewport: { width: 1366, height: 1024 },
    launchOptions: process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {} },
  webServer: [
    { command: 'node tests/backend-server.js', url: 'http://127.0.0.1:8001/api/health', env: backendEnv, reuseExistingServer: false },
    { command: 'npm run dev', url: 'http://127.0.0.1:5173', env: backendEnv, reuseExistingServer: false },
    { command: 'node tests/baseline-server.js', url: 'http://127.0.0.1:5174', reuseExistingServer: false },
    { command: 'npm run preview', url: 'http://127.0.0.1:4173', env: backendEnv, reuseExistingServer: false },
    { command: 'npm run preview -- --outDir dist-production --port 4273', url: 'http://127.0.0.1:4273', env: backendEnv, reuseExistingServer: false },
    { command: 'npm run preview -- --outDir dist-host --port 4373', url: 'http://127.0.0.1:4373', env: backendEnv, reuseExistingServer: false },
  ],
});
