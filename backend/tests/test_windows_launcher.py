"""Actual loopback TLS and supervised Windows startup. No external network."""
from pathlib import Path
import importlib.util
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


ROOT=Path(__file__).resolve().parents[2]


def launch_environment(storage):
    return {**os.environ,'ADMIN_USERNAME':'startup-test','ADMIN_PASSWORD':secrets.token_urlsafe(24),
            'BOOTH_PAIRING_KEY':secrets.token_urlsafe(24),'PYTHONUTF8':'1','APP_ENV':'development',
            'OPERATION_MODE':'development','OSA_STORAGE_ROOT':str(storage),
            'OSA_FRONTEND_DIST':str(ROOT/'frontend/dist-host'),'CAMERA_ADAPTER':'mock','PRINTER_MODE':'mock',
            'GOOGLE_DRIVE_ENABLED':'false'}


def test_lifespan_failure_reports_real_exception_and_nonzero_exit(tmp_path):
    # Reproduce a free TCP port with a held runtime lease, before any DB migration/OAuth.
    spec=importlib.util.spec_from_file_location('runtime_lock_test',ROOT/'backend/app/runtime_lock.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    storage=tmp_path/'locked-runtime'
    with socket.socket() as free:
        free.bind(('127.0.0.1',0));port=free.getsockname()[1]
    lease=module.RuntimeLock(storage/'.host-app.lock').acquire()
    try:
        result=subprocess.run([sys.executable,str(ROOT/'scripts/serve_app.py'),'--role','private',
            '--port',str(port),'--shutdown-file',str(tmp_path/'stop')],env=launch_environment(storage),
            capture_output=True,timeout=15)
    finally:lease.close()
    output=(result.stdout+result.stderr).decode('utf-8',errors='replace')
    assert result.returncode==3,output
    assert 'RuntimeError: Another process already owns this runtime service: .host-app.lock' in output
    assert not (storage/'photobooth.sqlite3').exists()


def test_genuine_port_conflict_captures_backend_stderr(tmp_path):
    storage=tmp_path/'conflict-runtime'
    with socket.socket() as listener:
        if os.name=='nt':listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        listener.bind(('127.0.0.1',0));listener.listen()
        port=listener.getsockname()[1]
        result=subprocess.run([sys.executable,str(ROOT/'scripts/run_host.py'),'--no-prompt','--port',str(port),
            '--storage-root',str(storage)],env=launch_environment(storage),capture_output=True,timeout=20)
        assert listener.getsockname()[1]==port  # The unrelated listener is untouched.
    output=(result.stdout+result.stderr).decode('utf-8',errors='replace')
    assert result.returncode!=0,output
    assert 'backend exit code=' in output and 'Captured stdout/stderr:' in output
    assert 'error while attempting to bind' in output.lower()
    logs=list((storage/'.run-control').glob('*.stderr.log'))
    assert logs and 'error while attempting to bind' in logs[0].read_text(encoding='utf-8').lower()


def test_launcher_bypasses_proxy_and_cleans_children_after_launcher_crash(tmp_path):
    storage=tmp_path/'owned-runtime';env=launch_environment(storage)
    env.update(HTTP_PROXY='http://127.0.0.1:1',HTTPS_PROXY='http://127.0.0.1:1',
               ALL_PROXY='http://127.0.0.1:1',NO_PROXY='',http_proxy='http://127.0.0.1:1',no_proxy='')
    with socket.socket() as free:free.bind(('127.0.0.1',0));port=free.getsockname()[1]
    command=[sys.executable,str(ROOT/'scripts/run_host.py'),'--no-prompt','--port',str(port),
             '--storage-root',str(storage)]
    with (tmp_path/'launcher.log').open('wb') as log:
        process=subprocess.Popen(command,env=env,stdout=log,stderr=log)
        manifest=storage/'.operator-run.json'
        try:
            with httpx.Client(trust_env=False,timeout=.5) as client:
                for _ in range(100):
                    assert process.poll() is None,(tmp_path/'launcher.log').read_text(encoding='utf-8')
                    if manifest.exists():break
                    time.sleep(.1)
                else:raise AssertionError('Launcher never became ready through direct localhost')
                health=client.get(f'http://127.0.0.1:{port}/api/health')
                assert health.status_code==200 and health.json()['startup_id']
                assert client.get(f'http://127.0.0.1:{port}/api/admin/sessions').status_code==401
            data=json.loads(manifest.read_text(encoding='utf-8'))
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(data['launcher_pid']),'/F'],check=True,capture_output=True)
                process.wait(timeout=10)
                spec=importlib.util.spec_from_file_location('runtime_lock_crash',ROOT/'backend/app/runtime_lock.py')
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                for _ in range(50):
                    try:
                        module.RuntimeLock(storage/'.host-app.lock').acquire().close();break
                    except RuntimeError:time.sleep(.1)
                else:raise AssertionError('Orphaned Host retained its OS lease after launcher crash')
                with socket.socket() as probe:
                    probe.settimeout(.5)
                    assert probe.connect_ex(('127.0.0.1',port))!=0
        finally:
            if process.poll() is None:
                subprocess.run([sys.executable,str(ROOT/'scripts/stop_host.py'),'--storage-root',str(storage)],
                               env=env,capture_output=True,timeout=40)
                process.wait(timeout=10)


def test_launcher_tls_secure_cookies_exclusive_runtime_and_safe_stop(tmp_path):
    root=Path(__file__).resolve().parents[2]
    openssl=os.environ.get('OPENSSL_COMMAND') or shutil.which('openssl') or str(Path(os.environ.get('ProgramFiles',''))/'Git/usr/bin/openssl.exe')
    if not Path(openssl).is_file():pytest.skip('OpenSSL unavailable for ephemeral loopback certificate')
    cert=tmp_path/'localhost.crt';key=tmp_path/'localhost.key'
    subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),
                    '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-days','1'],check=True,capture_output=True)
    with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    storage=tmp_path/'runtime';pair=secrets.token_urlsafe(24)
    env={**os.environ,'ADMIN_USERNAME':'tls-host','ADMIN_PASSWORD':secrets.token_urlsafe(24),'BOOTH_PAIRING_KEY':pair,'PYTHONUTF8':'1'}
    command=[sys.executable,str(root/'scripts/run_host.py'),'--no-prompt','--profile','https','--mode','rehearsal','--allow-mock-hardware','--public-url','https://photos.example.test',
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
