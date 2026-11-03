import {defineConfig} from '@playwright/test';
import {existsSync} from 'node:fs';
const chrome=process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe';
export default defineConfig({testDir:'./tests/mobile-qr',workers:1,timeout:60000,expect:{timeout:15000},
  outputDir:'test-results/mobile-qr',use:{baseURL:'http://localhost:8010',headless:true,
    viewport:{width:1180,height:820},launchOptions:existsSync(chrome)?{executablePath:chrome}:{}}});
