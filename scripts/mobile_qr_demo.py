"""Temporary, supervised mobile QR demo. Only the photo gateway enters the tunnel."""
import argparse
import base64
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, build_opener
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.runtime_lock import RuntimeLock
from app.services.images import atomic_write
from owned_processes import OwnedProcesses
from host_environment import load_environment
from app.services.public_gateway import DENIED, GatewayCheckError, verify_isolation

def write_json(path,data):
    atomic_write(path,json.dumps(data,indent=2).encode())
    path.chmod(0o600)

def get(url,timeout=8,local=False):
    request=Request(url,headers={'User-Agent':'AmazingRaceMobileQRTest/1.0','Cache-Control':'no-cache'})
    try:
        response=build_opener(ProxyHandler({})).open(request,timeout=timeout)
        with response:return response.status,response.read(),{name.lower():value for name,value in response.headers.items()}
    except HTTPError as error:return error.code,error.read(),{name.lower():value for name,value in error.headers.items()}

def denied(base,local):
    return verify_isolation(base)


def wait_for_proof(check,seconds=40):
    deadline=time.monotonic()+seconds
    while True:
        try:return check()
        except GatewayCheckError as error:
            if not error.retryable or time.monotonic()>=deadline:raise
            time.sleep(min(1,max(0,deadline-time.monotonic())))

def find_cloudflared():
    candidates=[shutil.which('cloudflared')]
    for variable in ('ProgramFiles','ProgramFiles(x86)','LOCALAPPDATA'):
        if os.environ.get(variable):candidates.append(str(Path(os.environ[variable])/'cloudflared'/'cloudflared.exe'))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            subprocess.run([candidate,'--version'],check=True,stdout=subprocess.DEVNULL)
            return candidate
    winget=shutil.which('winget')
    if not winget:raise RuntimeError('Install official Cloudflare.cloudflared with winget first.')
    subprocess.run([winget,'install','--exact','--id','Cloudflare.cloudflared','--source','winget',
                    '--accept-package-agreements','--accept-source-agreements','--disable-interactivity'],check=True)
    for variable in ('ProgramFiles','ProgramFiles(x86)'):
        candidate=Path(os.environ.get(variable,''))/'cloudflared'/'cloudflared.exe'
        if candidate.is_file():
            subprocess.run([str(candidate),'--version'],check=True)
            return str(candidate)
    raise RuntimeError('cloudflared installed but executable not found. Restart terminal and retry.')

def samples(settings,credentials,credentials_path):
    """Only synthetic fixtures in dedicated storage; restart reuses IDs/files."""
    from PIL import Image,ImageDraw
    from app.services.repository import Repository
    from app.services.images import validate_image
    repo=Repository(settings);owner=credentials['sample_owner'];result=[]
    for count in (4,6):
        sid=credentials['samples'].get(str(count))
        if sid:state=repo.get(sid,owner)
        else:
            state=repo.create(owner,str(uuid.uuid4()),{'layout':'landscape_4' if count==4 else 'grid2x3','slot_count':count})
            sid=state['session_id'];credentials['samples'][str(count)]=sid
            write_json(credentials_path,credentials)
        if state['status']!='completed':
            width,height=(1200,800) if count==4 else (800,1200)
            canvas=Image.new('RGB',(width,height),'#102546');draw=ImageDraw.Draw(canvas)
            draw.text((25,25),'AMAZING RACE 2026 - MOBILE QR TEST / DEMO',fill='white')
            rows=count//2
            for slot in range(count):
                x=25+(slot%2)*(width//2);y=80+(slot//2)*((height-110)//rows)
                draw.rounded_rectangle((x,y,x+width//2-50,y+(height-110)//rows-20),radius=15,fill=('#2458d3' if slot%2 else '#0ea5e9'))
                draw.text((x+20,y+20),f'DEMO {slot+1}',fill='white')
            output=BytesIO();canvas.save(output,'PNG');image=validate_image(output.getvalue(),'image/png',settings)
            stored={photo['slot_index'] for photo in state['photos']}
            for slot in range(count):
                if slot not in stored:state=repo.upload_photo(sid,owner,str(uuid.uuid4()),slot,'demo',image)
            if not state['composite']:
                state=repo.upload_composite(sid,owner,str(uuid.uuid4()),state['shots_revision'],{'fixture':'mobile-qr-demo'},image)
            cid=state['composite']['id'];state=repo.complete(sid,owner,str(uuid.uuid4()),cid)
        if settings.google_drive_enabled:
            # These operator-owned fixtures alone may migrate from the local
            # demo; never enqueue arbitrary historical/customer sessions here.
            with repo.db.connect() as db:repo.drive.queue(db,state['composite']['id'])
            # The Host worker retries this durable queue independently. A
            # checksum-verified staged composite is sufficient for sharing.
        if not state.get('share'):
            state=repo.sharing.finalize(sid,owner,str(uuid.uuid4()),state['composite']['id'])
        else:state=repo.get(sid,owner)
        with repo.db.connect() as db:
            row=db.execute('SELECT path,sha256 FROM composites WHERE id=?',(state['composite']['id'],)).fetchone()
        result.append({'session_id':sid,'share':state['share'],'composite_path':row['path'],'sha256':row['sha256']})
    return result

def verify(base,fixtures,local=False):
    from PIL import Image
    import zxingcpp
    tokens=[]
    for fixture in fixtures:
        token=fixture['share']['share_url'].rsplit('/',1)[1];tokens.append(token);route='/p/'+token
        status,html,_=get(base+route,local=local)
        if status!=200 or b'guestPhoto' not in html:raise RuntimeError('Guest Photo Page failed')
        status,image,_=get(base+route+'/image',local=local)
        status2,download,headers=get(base+route+'/download',local=local)
        if status!=200 or status2!=200 or image!=download:raise RuntimeError('Photo/download mismatch')
        Image.open(BytesIO(download)).verify()
        if 'attachment' not in headers.get('content-disposition',''):raise RuntimeError('Download is not an attachment')
        status,qr,_=get(base+route+'/qr.png',local=local)
        decoded=zxingcpp.read_barcode(Image.open(BytesIO(qr))) if status==200 else None
        if not decoded or decoded.text!=fixture['share']['share_url']:raise RuntimeError('QR content mismatch')
    if len(set(tokens))!=len(tokens):raise RuntimeError('Sessions did not receive distinct tokens')


def existing_photos(settings):
    """Reuse existing valid shares only. Never confirm, upload or enqueue customer photos."""
    from app.services.repository import Repository
    from fastapi import HTTPException
    repo=Repository(settings);result=[]
    with repo.db.connect() as db:
        rows=db.execute('''SELECT c.id,c.session_id,c.path,c.sha256 FROM composites c
            JOIN sessions s ON s.composite_id=c.id JOIN shares h ON h.composite_id=c.id
            WHERE s.status='completed' AND h.revoked_at IS NULL ORDER BY h.created_at DESC LIMIT 10''').fetchall()
        for row in rows:
            if os.environ.get('MOBILE_QR_TEST_SESSION_ID') and row['session_id']!=os.environ['MOBILE_QR_TEST_SESSION_ID']:continue
            share=repo.sharing.metadata(db,row['id'])
            if not share:continue
            try:repo.sharing.lookup(share['share_url'].rsplit('/',1)[1])
            except HTTPException:continue  # Includes pending Drive uploads.
            result.append({'session_id':row['session_id'],'share':share,'composite_path':row['path'],'sha256':row['sha256']})
            if len(result)==2:break
    return result

def environment(home,credentials,port,require_drive=False):
    env=dict(os.environ)
    env.update(APP_ENV='development',OPERATION_MODE='rehearsal',ALLOW_MOCK_HARDWARE='true',
        OSA_STORAGE_ROOT=str(home/'storage'),OSA_FRONTEND_DIST=str(ROOT/'frontend/dist-host'),
        ADMIN_USERNAME=credentials['username'],ADMIN_PASSWORD=credentials['password'],
        BOOTH_PAIRING_KEY=credentials['pairing_code'],CAMERA_ADAPTER='mock',CAMERA_GUEST_ENABLED='true',
        CAMERA_ALLOW_FAULTS='false',PRINTER_MODE='mock',ENABLE_PHYSICAL_PRINTING='false',
        PUBLIC_BASE_URL=f'http://localhost:{port}',GUEST_SESSION_IDLE_SECONDS='0',MOBILE_QR_PHOTO_ONLY='true',
        PYTHONUTF8='1',OSA_LOG_DIRECTORY=str(home/'logs'))
    env['GOOGLE_DRIVE_ENABLED']=str(require_drive).lower()
    return env

def serve(args):
    started=time.perf_counter();performance={}
    home=args.home;home.mkdir(parents=True,exist_ok=True)
    lease=RuntimeLock(home/'supervisor.lock').acquire()
    run_id=uuid.uuid4().hex;stop=home/'stop';stop.unlink(missing_ok=True)
    state=home/'status.json';credentials_path=home/'operator.json';children=[];logs=[]
    storage=args.storage_root if args.attach_host else home/'storage'
    origin_file=storage/'.mobile-qr-origin.json'
    owned=OwnedProcesses()
    try:
        write_json(state,{'phase':'starting','run_id':run_id})
        if credentials_path.exists():credentials=json.loads(credentials_path.read_text(encoding='utf-8'))
        else:
            credentials={'username':'mobile-test-host','password':secrets.token_urlsafe(24),
                         'pairing_code':secrets.token_urlsafe(24),'sample_owner':secrets.token_urlsafe(48),'samples':{}}
            write_json(credentials_path,credentials)
        cloudflared=find_cloudflared()
        if not (ROOT/'frontend/dist-host/index.html').is_file():
            npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm')
            if not npm:raise RuntimeError('Node/npm required to build Host frontend')
            subprocess.run([npm,'run','build:host'],cwd=ROOT/'frontend',check=True)
        env=environment(home,credentials,args.host_port,args.require_drive)
        from app.config import Settings
        settings=Settings(home/'storage',app_env='development',operation_mode='rehearsal',allow_mock_hardware=True,
                          public_base_url=f'http://localhost:{args.host_port}',google_drive_enabled=args.require_drive)
        if args.attach_host:
            status_code,payload,_=get(f'http://127.0.0.1:{args.host_port}/api/health',local=True)
            health=json.loads(payload)
            if status_code!=200 or health.get('status')!='ok' or health.get('phase')!=6:
                raise RuntimeError('Start the existing Photobooth Host first; no duplicate backend will be started.')
            if not health['sharing'].get('temporary_origin_supported') or health['sharing'].get('app_env')!='development':
                raise RuntimeError('Quick Tunnel testing requires a development/rehearsal Host. Event/production settings were not changed.')
            # Match the active host storage and Drive mode; never disable its queue.
            import dataclasses
            expected=hashlib.sha256(str(storage.resolve()).encode()).hexdigest()
            if health.get('runtime_id')!=expected:
                raise RuntimeError('Host runtime does not match --storage-root (or backend needs restart). No tunnel started.')
            drive=health.get('storage',{}).get('provider')=='google_drive'
            if args.require_drive and not drive:
                raise RuntimeError('Active Host has Google Drive disabled. Configure Drive on that Host first; its settings were not changed.')
            settings=dataclasses.replace(settings,storage_root=storage,google_drive_enabled=drive,
                google_oauth_client_file=Path(os.environ['GOOGLE_OAUTH_CLIENT_FILE']).resolve() if os.environ.get('GOOGLE_OAUTH_CLIENT_FILE') else None)
            env=dict(os.environ)
            env.update(OSA_STORAGE_ROOT=str(storage),APP_ENV='development',OPERATION_MODE=health['operation_mode'],
                ALLOW_MOCK_HARDWARE=str(health['operation_mode']=='rehearsal').lower(),GOOGLE_DRIVE_ENABLED=str(drive).lower(),
                PUBLIC_BASE_URL=f'http://localhost:{args.host_port}',MOBILE_QR_PHOTO_ONLY='true',PYTHONUTF8='1',
                OSA_LOG_DIRECTORY=str(home/'logs'))
            env.pop('OSA_FRONTEND_DIST',None)  # Gateway never serves booth/admin assets or needs kiosk credentials.
        env['PHOTOBOOTH_OWNED_JOB']=owned.name
        if args.require_drive and not args.attach_host:
            from app.services.drive_client import GoogleDriveClient
            GoogleDriveClient(settings).privacy()
        def launch(command,label):
            log=open(home/(label+'.log'),'ab');logs.append(log)
            child=subprocess.Popen(command,cwd=ROOT/'backend',env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            children.append(child);return child
        def track(child):owned.add(child);return child
        private=None if args.attach_host else track(launch([sys.executable,str(ROOT/'scripts/serve_app.py'),'--role','private','--port',str(args.host_port),
                        '--shutdown-file',str(home/'private.stop')],'host'))
        public=launch([sys.executable,str(ROOT/'scripts/serve_app.py'),'--role','public','--port',str(args.public_port),
                       '--shutdown-file',str(home/'public.stop')],'public')
        track(public)
        local=f'http://127.0.0.1:{args.public_port}'
        for _ in range(40):
            if stop.exists():raise RuntimeError('Stopped during startup')
            if (private is not None and private.poll() is not None) or public.poll() is not None:raise RuntimeError('Photo service failed; check host.log/public.log. No unrelated process was killed.')
            try:
                status,data,_=get(f'http://127.0.0.1:{args.host_port}/api/health',timeout=1,local=True)
                if status==200 and json.loads(data)['sharing'].get('temporary_origin_supported'):
                    break
            except (OSError,ValueError,URLError):pass
            time.sleep(.2)
        else:raise RuntimeError('Local photo-only isolation checks did not pass. Tunnel NOT started.')
        wait_for_proof(lambda:denied(local,local=True),seconds=15)
        fixtures=existing_photos(settings) if args.attach_host else samples(settings,credentials,credentials_path)
        original_hashes={item['composite_path']:item['sha256'] for item in fixtures}
        verify(local,fixtures,local=True)
        performance['gateway_start_ms']=round((time.perf_counter()-started)*1000,1)
        write_json(origin_file,{'phase':'connecting','run_id':run_id,'expires_at':time.time()+300})
        # Isolation has passed before cloudflared can expose this loopback port.
        tunnel_log=home/'cloudflared.log'
        log_offset=tunnel_log.stat().st_size if tunnel_log.exists() else 0
        tunnel=launch([cloudflared,'tunnel','--no-autoupdate','--protocol','http2','--url',local],'cloudflared')
        track(tunnel)
        origin=None
        for _ in range(240):
            if stop.exists():raise RuntimeError('Stopped during tunnel startup')
            if tunnel.poll() is not None:raise RuntimeError('Quick Tunnel failed; check cloudflared.log')
            content=tunnel_log.read_bytes()[log_offset:].decode('utf-8',errors='replace')
            matches=re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com',content)
            if matches:origin=matches[-1]
            if origin and 'Registered tunnel connection' in content:break
            time.sleep(.25)
        if not origin:raise RuntimeError('cloudflared did not return an HTTPS Quick Tunnel URL')
        # Do not advertise a public-ready QR until the live HTTPS gateway is verified.
        proof_started=time.perf_counter()
        try:
            wait_for_proof(lambda:denied(origin,local=False))
        finally:
            performance['https_verification_ms']=round((time.perf_counter()-proof_started)*1000,1)
        write_json(origin_file,{'phase':'ready','origin':origin,'run_id':run_id,'expires_at':time.time()+300,'isolation_verified':True})
        fixtures=existing_photos(settings) if args.attach_host else samples(settings,credentials,credentials_path)
        last_error=None
        for _ in range(3):
            if tunnel.poll() is not None:raise RuntimeError('Tunnel stopped before HTTPS verification')
            try:verify(origin,fixtures);break
            except (OSError,RuntimeError,URLError) as error:
                last_error=error;time.sleep(1)
        else:raise RuntimeError('Public HTTPS photo verification failed: '+type(last_error).__name__+'. Check direct HTTPS connectivity; tunnel will be stopped.')
        for relative,expected in original_hashes.items():
            if hashlib.sha256((settings.storage_root/relative).read_bytes()).hexdigest()!=expected:raise RuntimeError('Completed composite unexpectedly changed')
        cards=[]
        for index,fixture in enumerate(fixtures):
            url=fixture['share']['share_url']
            _,png,_=get(local+'/p/'+url.rsplit('/',1)[1]+'/qr.png',local=True)
            atomic_write(home/f'sample-{index+1}-qr.png',png)
            cards.append(f'<section><h2>Ảnh mẫu DEMO {4 if index==0 else 6} ảnh</h2><img width="280" alt="QR ảnh test" src="data:image/png;base64,{base64.b64encode(png).decode()}"><p><a href="{url}">Mở / tải ảnh test</a></p></section>')
        html='<!doctype html><html lang="vi"><meta charset="utf-8"><title>Mobile QR test</title><style>body{font:18px system-ui;background:#f0f7ff;text-align:center;color:#18386e}section{display:inline-block;background:white;padding:24px;margin:12px;border-radius:20px}</style><h1>AMAZING RACE 2026 · Mobile QR test</h1><p>Tắt Wi-Fi điện thoại, bật 4G/5G và quét QR. Laptop phải đang online.</p>'+''.join(cards)+f'<p><a href="http://localhost:{args.host_port}/booth">Mở Photobooth trên laptop</a></p><p>Tunnel tạm thời; link ngừng hoạt động khi dừng demo.</p></html>'
        atomic_write(home/'mobile-test.html',html.encode('utf-8'))
        status={'phase':'running','run_id':run_id,'origin':origin,'booth_url':f'http://localhost:{args.host_port}/booth',
                'admin_url':f'http://localhost:{args.host_port}/admin','public_port':args.public_port,
                'operator_file':str(credentials_path),'samples':[item['share']['share_url'] for item in fixtures],
                'test_page':str(home/'mobile-test.html'),
                'drive_enabled':settings.google_drive_enabled,'attach_host':args.attach_host,'host_port':args.host_port,
                'test_session_id':os.environ.get('MOBILE_QR_TEST_SESSION_ID'),
                'storage_root':str(storage),
                'verified_photo_count':len(fixtures),
                'checks':('HTTP isolation, HTTPS pages, image/download, distinct tokens, QR decode, unchanged composites PASS'
                          if fixtures else 'HTTP/HTTPS route isolation PASS; photo/download/QR verification awaits a completed available share'),
                'phone_scan':'NOT TESTED','performance':performance}
        write_json(state,status)
        last_probe=0
        while not stop.exists():
            if any(child.poll() is not None for child in children):raise RuntimeError('An owned demo service stopped; restarting all demo services is required')
            if time.time()-last_probe>10:
                try:
                    code,body,_=get(origin+'/p/invalid',timeout=5)
                    if code!=404 or b'AMAZING RACE 2026' not in body:
                        raise RuntimeError('Photo gateway connection lost')
                    write_json(origin_file,{'phase':'ready','origin':origin,'run_id':run_id,'expires_at':time.time()+35,'isolation_verified':True})
                except (OSError,RuntimeError,URLError):
                    write_json(origin_file,{'phase':'disconnected','run_id':run_id,'expires_at':time.time()+35})
                last_probe=time.time()
            time.sleep(.5)
    except BaseException as error:
        write_json(state,{'phase':'error','run_id':run_id,'error':str(error),'performance':performance})
    finally:
        # Only Popen handles created by this supervisor are stopped. Never kill by
        # port, process name, or a PID read from an untrusted/stale manifest.
        for name in ('private.stop','public.stop'):(home/name).write_text('stop',encoding='utf-8')
        for child in reversed(children):
            if child.poll() is None:
                try:child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    if os.name=='nt':owned.close()
                    else:child.terminate()
                    child.wait(timeout=8)
        owned.close()
        for log in logs:log.close()
        if origin_file.exists():
            try:
                if json.loads(origin_file.read_text())['run_id']==run_id:
                    write_json(origin_file,{'phase':'disconnected','run_id':run_id,'expires_at':0})
            except (OSError,ValueError,KeyError):pass
        for name in ('private.stop','public.stop'):(home/name).unlink(missing_ok=True)
        if state.exists():
            current=json.loads(state.read_text())
            if current.get('phase')!='error':write_json(state,{'phase':'stopped','run_id':run_id})
        lease.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['start','serve','stop','status'])
    parser.add_argument('--home',type=Path,default=ROOT/'.tools/mobile-qr-demo')
    parser.add_argument('--host-port',type=int,default=8010);parser.add_argument('--public-port',type=int,default=8011)
    parser.add_argument('--require-drive',action='store_true',help='Require OAuth, Restricted ACL and synced private Drive storage before opening a tunnel')
    parser.add_argument('--attach-host',action='store_true',help='Reuse an existing Host and its storage; never start another private backend')
    parser.add_argument('--test-session-id',type=uuid.UUID,help='Restrict temporary public gateway to ONE disposable test session')
    parser.add_argument('--storage-root',type=Path,default=ROOT/'runtime')
    parser.add_argument('--env-file',type=Path)
    args=parser.parse_args();args.home=args.home.resolve();home=args.home
    args.storage_root=args.storage_root.expanduser().resolve()
    if args.test_session_id:os.environ['MOBILE_QR_TEST_SESSION_ID']=str(args.test_session_id)
    if args.env_file:os.environ.update(load_environment(args.env_file))
    if args.host_port==args.public_port or not all(1<=port<=65535 for port in (args.host_port,args.public_port)):parser.error('Distinct valid ports required')
    if not home.is_relative_to(ROOT/'.tools'):parser.error('Demo control/storage must remain under project .tools')
    if args.action=='start' and args.require_drive and not args.attach_host:
        from app.config import Settings
        from app.services.drive_client import GoogleDriveClient,DriveError
        settings=Settings(home/'storage',app_env='development',operation_mode='rehearsal',allow_mock_hardware=True,
                          google_drive_enabled=True)
        try:GoogleDriveClient(settings).privacy()
        except DriveError as error:raise RuntimeError('Drive preflight blocked; no new process/tunnel started. '+str(error)) from None
    if args.action=='serve':return serve(args)
    home.mkdir(parents=True,exist_ok=True);state=home/'status.json'
    def running():
        try:probe=RuntimeLock(home/'supervisor.lock').acquire()
        except RuntimeError:return True
        else:probe.close();return False
    if args.action=='stop':
        if not running():print('No active mobile demo. Saved photos and credentials retained.');return
        (home/'stop').write_text('stop',encoding='utf-8')
        for _ in range(160):
            if not running():print('Stopped only mobile QR demo services. Saved photos/Host settings retained.');return
            time.sleep(.2)
        raise RuntimeError('Graceful stop pending; inspect demo logs. No unrelated process was killed.')
    if args.action=='start' and not running():
        for name in ('private.stop','public.stop','stop'):(home/name).unlink(missing_ok=True)
        state.unlink(missing_ok=True)
        with open(home/'supervisor.log','ab') as log:
            subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'serve','--home',str(home),
                              '--host-port',str(args.host_port),'--public-port',str(args.public_port),
                              '--storage-root',str(args.storage_root)]+(['--attach-host'] if args.attach_host else [])+
                              (['--env-file',str(args.env_file.resolve())] if args.env_file else [])+
                              (['--require-drive'] if args.require_drive else []),
                cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    for _ in range(180):
        if state.exists():
            data=json.loads(state.read_text(encoding='utf-8'))
            if data['phase']=='running':
                if args.action=='start' and data.get('test_session_id')!=os.environ.get('MOBILE_QR_TEST_SESSION_ID'):
                    raise RuntimeError('Existing tunnel has a different test-session restriction; stop it explicitly first.')
                if args.action=='start' and (bool(data.get('attach_host'))!=args.attach_host or data.get('host_port',8010)!=args.host_port or data.get('public_port')!=args.public_port):
                    raise RuntimeError('A mobile tunnel already serves another Host/runtime. Stop it with stop_mobile_qr_demo.ps1 first; no duplicate tunnel was started.')
                if args.require_drive and not data.get('drive_enabled'):
                    raise RuntimeError('Existing demo is local-only. Configure Drive OAuth/privacy, stop that demo explicitly, then start with --require-drive. No duplicate service/tunnel was started.')
                print(json.dumps(data,indent=2));return
            if data['phase']=='error':raise RuntimeError(data['error'])
        if args.action=='status':print('Demo is not ready/running.');return
        time.sleep(1)
    raise RuntimeError('Setup still pending. Read .tools/mobile-qr-demo/supervisor.log or run status. Do not start another tunnel.')

if __name__=='__main__':
    try:main()
    except (RuntimeError,OSError,subprocess.CalledProcessError) as error:raise SystemExit(str(error))
