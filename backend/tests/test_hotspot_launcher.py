"""Hotspot routing and one real supervised listener, using disposable storage."""
import os
import secrets
import socket
import subprocess
import sys
import time

import httpx
import pytest

from test_windows_launcher import ROOT, launch_environment

sys.path.insert(0,str(ROOT/'scripts'))
import run_host


@pytest.mark.parametrize('address',['10.42.0.2','172.20.10.2','192.168.43.23'])
def test_automatic_address_tracks_default_route_without_sending_packets(monkeypatch,address):
    class Route:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def connect(self,destination):pass
        def getsockname(self):return (address,1234)
        def send(self,*args):pytest.fail('Detection must not send data')
    monkeypatch.setattr(run_host.socket,'socket',lambda *args:Route())
    assert run_host.detect_lan_ipv4()==address


@pytest.mark.parametrize('address',['127.0.0.1','0.0.0.0','169.254.1.2','8.8.8.8','::1'])
def test_no_public_loopback_or_link_local_address_is_advertised(address):
    with pytest.raises(ValueError):run_host.lan_ipv4(address)


def test_hotspot_listener_localhost_lan_pairing_auth_and_single_instance(tmp_path):
    try:lan=run_host.detect_lan_ipv4()
    except (OSError,ValueError):pytest.skip('No private default-route interface connected')
    # Use 8000 when free. Never stop or disturb an operator's existing server.
    with socket.socket() as free:
        try:free.bind(('0.0.0.0',8000));port=8000
        except OSError:
            free.bind(('0.0.0.0',0));port=free.getsockname()[1]
    env=launch_environment(tmp_path/'runtime')
    for name in ('HOST_BIND','HOST_LAN_IP','PUBLIC_BASE_URL','HOST_BEHIND_PROXY','PUBLIC_GATEWAY'):
        env.pop(name,None)
    command=[sys.executable,str(ROOT/'scripts/run_host.py'),'--profile','lan','--no-prompt',
             '--port',str(port),'--storage-root',str(tmp_path/'runtime')]
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    with (tmp_path/'launcher.log').open('wb') as log:
        process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=log,**flags)
        try:
            with httpx.Client(trust_env=False,timeout=2) as local,httpx.Client(base_url=f'http://{lan}:{port}',trust_env=False,timeout=2) as remote:
                for _ in range(150):
                    assert process.poll() is None,(tmp_path/'launcher.log').read_text(encoding='utf-8')
                    try:
                        if (tmp_path/'runtime/.operator-run.json').exists() and local.get(f'http://127.0.0.1:{port}/api/health').status_code==200:break
                    except httpx.TransportError:pass
                    time.sleep(.2)
                else:pytest.fail('Launcher readiness timeout')
                assert remote.get('/api/health').status_code==200
                assert remote.get('/').status_code==200
                assert remote.get('/booth').status_code==200
                assert remote.get('/api/admin/sessions').status_code==403
                assert remote.post('/api/admin/login',json={}).status_code==403
                assert remote.post('/api/sessions',json={}).status_code==401
                login=local.post(f'http://127.0.0.1:{port}/api/admin/login',headers={'X-OSA-Login':'1'},json={
                    'username':env['ADMIN_USERNAME'],'password':env['ADMIN_PASSWORD']})
                assert login.status_code==200
                pair=remote.post('/api/booth/pair',headers={'X-OSA-Pair':'1'},json={'key':env['BOOTH_PAIRING_KEY']})
                assert pair.status_code==200
                auth={'X-Booth-CSRF':pair.json()['csrf_token'],'Authorization':'Bearer '+secrets.token_urlsafe(32)}
                created=remote.post('/api/sessions',headers={**auth,'Idempotency-Key':secrets.token_urlsafe(24)},json={'layout':'landscape_4','slot_count':4})
                assert created.status_code==200,created.text
                base='/api/sessions/'+created.json()['session_id']+'/camera'
                assert remote.post(base+'/connect',headers=auth).status_code==200
                assert remote.post(base+'/live-view/start',headers=auth).status_code==200
                timings=[];sizes=[]
                for _ in range(5):
                    started=time.perf_counter();frame=remote.get(base+'/frame',headers=auth)
                    assert frame.status_code==200
                    timings.append(round((time.perf_counter()-started)*1000));sizes.append(len(frame.content))
                print(f'LAN {lan}:{port}: localhost=200, LAN=200, remote-admin=403; mock preview ms={timings}, bytes={sizes}')
                assert remote.post(base+'/disconnect',headers=auth).status_code==200
                duplicate=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,timeout=15,**flags)
                assert duplicate.returncode!=0 and process.poll() is None
                assert remote.get('/api/health').status_code==200
                if os.name=='nt':
                    listeners=subprocess.run(['netstat','-ano','-p','tcp'],capture_output=True,text=True,check=True).stdout
                    lines=[line.strip() for line in listeners.splitlines() if f'0.0.0.0:{port} ' in line and 'LISTENING' in line]
                    if lines:print('Actual listener: '+'; '.join(lines))
                    else:print('Windows socket/PID enumeration unavailable here; verified both interfaces by direct HTTP and Uvicorn bind log.')
                logs=(tmp_path/'runtime/.run-control').glob('*.private.stderr.log')
                assert any(f'Uvicorn running on http://0.0.0.0:{port}' in path.read_text(encoding='utf-8') for path in logs)
        finally:
            if process.poll() is None:
                stopped=subprocess.run([sys.executable,str(ROOT/'scripts/stop_host.py'),'--storage-root',str(tmp_path/'runtime')],cwd=ROOT,env=env,capture_output=True,timeout=40,**flags)
                assert stopped.returncode==0,stopped.stderr
                process.wait(timeout=10)
            assert process.returncode==0
