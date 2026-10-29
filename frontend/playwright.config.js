import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  workers: 1,
  timeout: 90000,
  use: { headless: true, viewport: { width: 1366, height: 1024 },
    launchOptions: process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {} },
  webServer: [
    { command: 'npm run dev', url: 'http://127.0.0.1:5173', reuseExistingServer: false },
    { command: 'node tests/baseline-server.js', url: 'http://127.0.0.1:5174', reuseExistingServer: false },
    { command: 'npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: false },
    { command: 'npm run preview -- --outDir dist-production --port 4273', url: 'http://127.0.0.1:4273', reuseExistingServer: false },
  ],
});
