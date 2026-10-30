import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';

// Isolated ports: this smoke test can run while the operator uses 8000/5173.
export default defineConfig({
  testDir:'./tests/qr-confirm',outputDir:'test-results/qr-confirm',workers:1,timeout:60000,
  use:{headless:true,launchOptions:process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {}},
  webServer:[
    {command:'python ../scripts/run_local_backend.py --port 8002',url:'http://127.0.0.1:8002/api/health',env:{
      OSA_STORAGE_ROOT:fileURLToPath(new URL('../.tools/qr-confirm-backend/',import.meta.url)),
      PRINTER_MODE:'mock',ENABLE_PHYSICAL_PRINTING:'false',
    }},
    {command:'npm run dev -- --port 5183',url:'http://127.0.0.1:5183',env:{OSA_BACKEND_URL:'http://127.0.0.1:8002'}},
  ],
});
