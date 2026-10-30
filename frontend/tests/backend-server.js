/** Local test backend only; separate storage, never the operator's runtime/. */
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const backend = fileURLToPath(new URL('../../backend/', import.meta.url));
const python = fileURLToPath(new URL(process.platform === 'win32'
  ? '../../backend/.venv/Scripts/python.exe' : '../../backend/.venv/bin/python', import.meta.url));
if (!existsSync(python)) throw new Error('Create backend/.venv and install requirements before E2E.');
const child = spawn(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', process.env.OSA_TEST_PORT || '8001'], {
  cwd: backend, stdio: 'inherit', env: {...process.env, PRINTER_MODE:'mock', ENABLE_PHYSICAL_PRINTING:'false',CAMERA_ADAPTER:'mock',CAMERA_GUEST_ENABLED:'true',CAMERA_ALLOW_FAULTS:'true'},
});
child.on('exit', code => process.exit(code || 0));
process.on('SIGTERM', () => child.kill());
process.on('SIGINT', () => child.kill());
