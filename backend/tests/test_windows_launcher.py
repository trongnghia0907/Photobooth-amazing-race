"""Actual loopback TLS and supervised Windows startup. No external network."""
from pathlib import Path
import json
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import time
import httpx
import pytest


def test_launcher_tls_secure_cookies_exclusive_runtime_and_safe_stop(tmp_path):
    root=Path(__file__).resolve().parents[2]
    openssl=shutil.which('openssl') or r'C:\Program Files\Git\usr\bin\openssl.exe'
    if not Path(openssl).is_file():pytest.skip('OpenSSL unavailable for ephemeral loopback certificate')
    cert=tmp_path/'localhost.crt';key=tmp_path/'localhost.key'
    subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),
                    '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-days','1'],check=True,capture_output=True)
    with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    storage=tmp_path/'runtime';pair=secrets.token_urlsafe(24)
    env={**os.environ,'ADMIN_USERNAME':'tls-host','ADMIN_PASSWORD':secrets.token_urlsafe(24),'BOOTH_PAIRING_KEY':pair,'PYTHONUTF8':'1'}
    command=[sys.executable,str(root/'scripts/run_host.py'),'--no-prompt','--profile','https','--public-url','https://photos.example.test',
             '--port',str(port),'--storage-root',str(storage),'--ssl-certfile',str(cert),'--ssl-keyfile',str(key)]
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    with (tmp_path/'server.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen(command,cwd=root,env=env,stdout=log,stderr=log,**flags)
        try:
            context=ssl.create_default_context(cafile=str(cert))
            with httpx.Client(base_url=f'https://127.0.0.1:{port}',verify=context,trust_env=False,timeout=2) as client:
                for _ in range(150):
                    assert process.poll() is None,(tmp_path/'server.log').read_text(encoding='utf-8')
                    try:
                        if client.get('/api/health').status_code==200 and (storage/'.operator-run.json').exists():break
                    except httpx.TransportError:pass
                    time.sleep(.2)
                else:raise AssertionError('HTTPS launcher timeout')
                assert client.get('/booth').status_code==200
                result=client.post('/api/booth/pair',headers={'X-OSA-Pair':'1'},json={'key':pair})
                assert result.status_code==200 and 'Secure' in result.headers['set-cookie']
                assert client.get('/api/booth/me').status_code==200
                assert client.get('/docs').status_code==404
                login=client.post('/api/admin/login',headers={'X-OSA-Login':'1'},json={'username':env['ADMIN_USERNAME'],'password':env['ADMIN_PASSWORD']})
                assert login.status_code==200 and 'Secure' in login.headers['set-cookie']
                assert client.get('/api/admin/sessions').status_code==200
                assert client.post('/api/admin/logout',headers={'X-CSRF-Token':login.json()['csrf_token']}).status_code==200
                assert client.get('/api/admin/sessions').status_code==401
            duplicate=subprocess.run(command,cwd=root,env=env,capture_output=True,timeout=20,**flags)
            assert duplicate.returncode!=0
            live_backup=subprocess.run([sys.executable,str(root/'scripts/backup_runtime.py'),'--storage-root',str(storage),'--output',str(tmp_path/'unsafe-live-backup')],capture_output=True,timeout=10,**flags)
            assert live_backup.returncode!=0 and not (tmp_path/'unsafe-live-backup').exists()
        finally:
            if process.poll() is None:
                stopped=subprocess.run([sys.executable,str(root/'scripts/stop_host.py'),'--storage-root',str(storage)],capture_output=True,timeout=40,**flags)
                assert stopped.returncode==0,stopped.stderr
                process.wait(timeout=10)
            assert process.returncode==0
    assert not (storage/'.operator-run.json').exists()
