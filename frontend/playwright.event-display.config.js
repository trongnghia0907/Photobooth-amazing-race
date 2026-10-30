import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests/event-display',outputDir:'test-results/event-display',workers:1,timeout:180000,
  expect:{timeout:15000},use:{headless:true,viewport:{width:1920,height:1080},actionTimeout:15000,navigationTimeout:15000,trace:'retain-on-failure',
    launchOptions:process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{}}});
