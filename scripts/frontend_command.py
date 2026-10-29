"""Run frontend tooling with workspace-local Node when Node is not on PATH.

Normal installed Node users should use npm directly. This helper does not install
packages globally or modify system settings.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
env = os.environ.copy()
portable = root/'.tools/node-v24.22.2-win-x64'
if portable.exists():
 env['PATH'] = str(portable)+os.pathsep+env.get('PATH','')
for name in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']:
 env.pop(name,None)
env['CHROME_PATH'] = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
npm = str(portable/'npm.cmd') if portable.exists() else shutil.which('npm')
if not npm:
 raise SystemExit('Install Node.js or run scripts/setup_test_tools.py first.')
raise SystemExit(subprocess.call([npm,*sys.argv[1:]],cwd=root/'frontend',env=env))
