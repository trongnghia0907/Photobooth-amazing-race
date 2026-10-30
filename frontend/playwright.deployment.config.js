import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests/deployment',outputDir:'test-results/deployment',workers:1,timeout:240000,expect:{timeout:15000},
  use:{headless:true,viewport:{width:1180,height:820},launchOptions:process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{}}});
