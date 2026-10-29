import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const backendEnv = {
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
  ],
});
