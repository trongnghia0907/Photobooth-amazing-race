import { defineConfig, searchForWorkspaceRoot } from 'vite';
import { fileURLToPath } from 'node:url';

const target = process.env.OSA_BACKEND_URL || 'http://127.0.0.1:8000';
const proxy = { '/api': { target, changeOrigin: true }, '/p': { target, changeOrigin: true }, '/admin': { target, changeOrigin: true }, '/event-display': { target, changeOrigin: true } };
export default defineConfig({
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy,
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), fileURLToPath(new URL('../theme/Theme-ptb-final.png', import.meta.url))] } },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy },
  build: { target: 'es2022' },
});
