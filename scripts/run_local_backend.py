"""Explicit local QR development mode, without changing the system environment."""
from pathlib import Path
import argparse
import os
import subprocess
import getpass

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description='Run OSA backend with real localhost share URLs')
parser.add_argument('--port', type=int, default=8000)
parser.add_argument('--reload', action='store_true')
parser.add_argument('--admin', action='store_true', help='Prompt for host credentials (password is hidden)')
args = parser.parse_args()
if not 1 <= args.port <= 65535:
    parser.error('port must be 1..65535')
python = root / 'backend/.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
if not python.is_file():
    raise SystemExit('Create backend/.venv and install backend/requirements.lock.txt first.')
env = {**os.environ, 'APP_ENV': 'development', 'PUBLIC_BASE_URL': f'http://localhost:{args.port}',
       'PRINTER_MODE':'mock','ENABLE_PHYSICAL_PRINTING':'false',
       'CAMERA_ADAPTER':'mock','CAMERA_GUEST_ENABLED':'true'}
if args.admin:
    env['ADMIN_USERNAME'] = os.environ.get('ADMIN_USERNAME') or input('Host username: ').strip()
    env['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD') or getpass.getpass('Host password (12+ characters): ')
    if not env['ADMIN_USERNAME'] or len(env['ADMIN_PASSWORD']) < 12:
        raise SystemExit('Username required and password must have at least 12 characters.')
command = [str(python), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(args.port)]
if args.reload:
    command.append('--reload')
print(f'Local QR development: http://localhost:{args.port}', flush=True)
print('QR opens on THIS computer only, not other phones. No public tunnel is started.', flush=True)
print('Printer: MOCK only (no paper). Host Dashboard: /admin', flush=True)
try:
    raise SystemExit(subprocess.call(command, cwd=root / 'backend', env=env))
except KeyboardInterrupt:
    raise SystemExit(0)
