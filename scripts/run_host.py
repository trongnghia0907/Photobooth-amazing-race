"""Windows-first same-origin host launcher. Never starts a public tunnel."""
import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from urllib.error import URLError
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.runtime_lock import RuntimeLock
from host_environment import load_environment,restore_drive_setting,save_drive_setting
from owned_processes import OwnedProcesses


def lan_ipv4(value):
    try:
        address=ipaddress.ip_address(value)
        if address.version==4 and any(address in ipaddress.ip_network(net) for net in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
            return str(address)
    except ValueError:pass
    raise ValueError('LAN requires a private IPv4 address; check ipconfig and use --lan-ip IP if automatic detection selects a VPN.')


def detect_lan_ipv4():
    # UDP connect only asks the OS which interface routes outbound traffic.
    # No packets are sent and Internet connectivity is not required.
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as route:
        route.connect(('1.1.1.1',80))
        return lan_ipv4(route.getsockname()[0])


def main():
    parser=argparse.ArgumentParser(description='Run built AMAZING RACE 2026 kiosk + API without Vite')
    parser.add_argument('--env-file',type=Path)
    parser.add_argument('--profile',choices=['local','lan','https'])
    parser.add_argument('--mode',choices=['development','rehearsal','event'])
    parser.add_argument('--allow-mock-hardware',action=argparse.BooleanOptionalAction,default=None)
    parser.add_argument('--storage-root',type=Path)
    parser.add_argument('--port',type=int)
    parser.add_argument('--bind')
    parser.add_argument('--lan-ip',help='Laptop private IPv4, or auto (default for LAN); uses the active default route')
    parser.add_argument('--public-url')
    parser.add_argument('--public-gateway',action=argparse.BooleanOptionalAction,default=None,help='Start photo-only gateway on loopback; does not expose Internet')
    parser.add_argument('--public-port',type=int)
    parser.add_argument('--camera',choices=['mock','vendor','uvc_demo','sony_zve10'])
    parser.add_argument('--printer',choices=['mock','windows','cups'])
    parser.add_argument('--enable-physical-printing',action=argparse.BooleanOptionalAction,default=None)
    parser.add_argument('--ssl-certfile',type=Path)
    parser.add_argument('--ssl-keyfile',type=Path)
    parser.add_argument('--tls-host',default='localhost',help='Private HTTPS hostname/IP matching the certificate, for health check and operator URL')
    parser.add_argument('--behind-proxy',action='store_true')
    parser.add_argument('--build',action='store_true')
    parser.add_argument('--no-prompt',action='store_true')
    parser.add_argument('--check',action='store_true',help='Validate configuration without starting services or hardware')
    args=parser.parse_args()
    try:env=load_environment(args.env_file)
    except (OSError,ValueError) as error:parser.error(str(error))
    def env_flag(name):
        value=env.get(name,'false').strip().lower()
        if value not in ('true','false'):parser.error(f'{name} must be true or false')
        return value=='true'
    args.profile=args.profile or env.get('HOST_PROFILE','local')
    if args.profile not in ('local','lan','https'):parser.error('HOST_PROFILE must be local, lan or https')
    args.port=args.port if args.port is not None else int(env.get('HOST_PORT','8000'))
    args.public_port=args.public_port if args.public_port is not None else int(env.get('PUBLIC_PORT','8001'))
    args.storage_root=args.storage_root or Path(env.get('OSA_STORAGE_ROOT',ROOT/'runtime'))
    args.bind=args.bind or env.get('HOST_BIND')
    args.lan_ip=args.lan_ip or env.get('HOST_LAN_IP')
    args.ssl_certfile=args.ssl_certfile or (Path(env['HOST_SSL_CERTFILE']) if env.get('HOST_SSL_CERTFILE') else None)
    args.ssl_keyfile=args.ssl_keyfile or (Path(env['HOST_SSL_KEYFILE']) if env.get('HOST_SSL_KEYFILE') else None)
    args.tls_host=env.get('HOST_TLS_HOST',args.tls_host) if args.tls_host=='localhost' else args.tls_host
    args.behind_proxy=args.behind_proxy or env_flag('HOST_BEHIND_PROXY')
    args.public_gateway=args.public_gateway if args.public_gateway is not None else env_flag('PUBLIC_GATEWAY')
    args.camera=args.camera or env.get('CAMERA_ADAPTER','mock')
    args.printer=args.printer or env.get('PRINTER_MODE','mock')
    mode=args.mode or env.get('OPERATION_MODE','event' if args.profile=='https' else 'development')
    expected_env='production' if args.profile=='https' else 'development'
    if env.get('APP_ENV',expected_env).strip().lower()!=expected_env:
        parser.error(f'{args.profile} profile requires APP_ENV={expected_env}; refusing to silently change environment')
    if args.allow_mock_hardware is not None:env['ALLOW_MOCK_HARDWARE']=str(args.allow_mock_hardware).lower()
    if args.enable_physical_printing is not None:env['ENABLE_PHYSICAL_PRINTING']=str(args.enable_physical_printing).lower()
    env.update(OPERATION_MODE=mode)
    if mode=='event' and args.profile!='https':parser.error('Event mode requires the HTTPS profile; use development/rehearsal for local/LAN demos')
    if mode=='event' and args.camera in ('mock','uvc_demo'):parser.error('Event mode blocks simulated camera capture. Select a verified physical adapter, or explicitly use rehearsal + --allow-mock-hardware')
    if not args.tls_host or any(c in args.tls_host for c in '/:@ \t\r\n'):parser.error('--tls-host must be a hostname or IPv4 without scheme/port')
    if not 1<=args.port<=65535 or not 1<=args.public_port<=65535 or args.public_port==args.port:parser.error('Invalid/distinct ports required')
    python=Path(env.get('PHOTOBOOTH_PYTHON',ROOT/'backend/.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')))
    if not python.is_file():parser.error('Create backend/.venv and install requirements.lock.txt first')
    if args.build:
        npm=env.get('NPM_COMMAND') or shutil.which('npm.cmd' if os.name=='nt' else 'npm')
        if not npm:parser.error('Install Node/npm first')
        subprocess.run([npm,'run','build:host'],cwd=ROOT/'frontend',env=env,check=True)
    dist=Path(env.get('OSA_FRONTEND_DIST',ROOT/'frontend/dist-host')).expanduser().resolve()
    if not (dist/'index.html').is_file():parser.error('Run cd frontend; npm.cmd ci; npm.cmd run build:host (or --build)')
    env.update(OSA_STORAGE_ROOT=str(args.storage_root.expanduser().resolve()),OSA_FRONTEND_DIST=str(dist),
               CAMERA_ADAPTER=args.camera,PRINTER_MODE=args.printer)
    env=restore_drive_setting(env,env['OSA_STORAGE_ROOT'])
    if not args.check:
        # A port can be free while an abandoned worker still owns the camera/DB runtime.
        # Probe the OS lease, never delete a lock file or infer ownership from its existence.
        try:RuntimeLock(Path(env['OSA_STORAGE_ROOT'])/'.host-app.lock').acquire().close()
        except RuntimeError as error:
            raise RuntimeError(f'{error}. An existing Host still owns this storage, even if port {args.port} is free. '
                               'Use stop_host.py or stop its original launcher; do not delete lock files.') from error
    env.setdefault('CAMERA_GUEST_ENABLED','true');env.setdefault('CAMERA_ALLOW_FAULTS','false')
    env.setdefault('ENABLE_PHYSICAL_PRINTING','false')
    def credential(name,prompt,minimum):
        value=env.get(name,'')
        if not value and not (args.no_prompt or args.check):value=getpass.getpass(prompt) if 'PASSWORD' in name or 'KEY' in name else input(prompt).strip()
        if len(value)<minimum:parser.error(f'{name} needs at least {minimum} characters; use environment or interactive prompt')
        env[name]=value
    credential('ADMIN_USERNAME','Host username: ',1)
    credential('ADMIN_PASSWORD','Host password (12+ characters, hidden): ',12)
    credential('BOOTH_PAIRING_KEY','Kiosk pairing code (16+ characters, hidden): ',16)
    if args.profile=='lan':
        auto_lan=not args.lan_ip or args.lan_ip=='auto'
        try:args.lan_ip=detect_lan_ipv4() if auto_lan else lan_ipv4(args.lan_ip)
        except (OSError,ValueError) as error:parser.error(f'Cannot detect the hotspot/LAN interface: {error}. Connect to the hotspot or specify --lan-ip from ipconfig.')
        bind=args.bind or '0.0.0.0'
        if bind!='0.0.0.0':parser.error('LAN profile requires --bind 0.0.0.0 to serve both localhost and hotspot devices; use --profile local for loopback only.')
        env.update(APP_ENV='development',ALLOW_LAN_HTTP='true',PUBLIC_BASE_URL=args.public_url or env.get('PUBLIC_BASE_URL') or f'http://{args.lan_ip}:{args.port}')
    elif args.profile=='https':
        origin=args.public_url or env.get('PUBLIC_BASE_URL','')
        if not origin.startswith('https://'):parser.error('--public-url HTTPS origin required')
        bind=args.bind or '127.0.0.1';env.update(APP_ENV='production',PUBLIC_BASE_URL=origin)
        env['ALLOW_LAN_HTTP']='false'
        if args.behind_proxy:
            if bind not in ('127.0.0.1','::1'):parser.error('Behind-proxy origin must bind loopback')
        elif not (args.ssl_certfile and args.ssl_keyfile and args.ssl_certfile.is_file() and args.ssl_keyfile.is_file()):
            parser.error('HTTPS needs --ssl-certfile and --ssl-keyfile, or an explicitly configured --behind-proxy on loopback')
    else:
        bind=args.bind or '127.0.0.1'
        if bind!='127.0.0.1':parser.error('Local profile uses 127.0.0.1; use --profile lan explicitly for LAN exposure')
        env.update(APP_ENV='development',ALLOW_LAN_HTTP='false',PUBLIC_BASE_URL=args.public_url or env.get('PUBLIC_BASE_URL') or f'http://localhost:{args.port}')
    # Validate config without printing sensitive values.
    validated=subprocess.run([str(python),'-c','from app.config import Settings; from app.services.sharing import public_origin; s=Settings.from_environment(); public_origin(s.public_base_url,allow_local=s.app_env=="development",allow_lan=s.allow_lan_http)'],cwd=ROOT/'backend',env=env)
    if validated.returncode:return validated.returncode
    if args.check:
        print(f'Configuration valid: {mode}, {args.profile}, camera={args.camera}, printer={args.printer}. Hardware/network acceptance still required.')
        return 0
    storage=Path(env['OSA_STORAGE_ROOT']);storage.mkdir(parents=True,exist_ok=True)
    lease=RuntimeLock(storage/'.launcher.lock').acquire()
    control=storage/'.run-control';control.mkdir(exist_ok=True)
    manifest=storage/'.operator-run.json';children=[];startup_logs={}
    try:owned=OwnedProcesses()
    except OSError:
        lease.close();raise
    startup_id=uuid.uuid4().hex
    env['PHOTOBOOTH_STARTUP_ID']=startup_id
    env['PHOTOBOOTH_OWNED_JOB']=owned.name
    def direct_open(url, timeout, context=None):
        """Open a local health URL directly; never route loopback through a proxy."""
        handlers=[urllib.request.ProxyHandler({})]
        if context is not None:handlers.append(urllib.request.HTTPSHandler(context=context))
        return urllib.request.build_opener(*handlers).open(
            urllib.request.Request(url,headers={'Accept':'application/json'}), timeout=timeout)
    def existing_photobooth(host, port, tls=False):
        """Return True only when the port answers as this Photobooth API."""
        scheme='https' if tls else 'http'
        probe_host=args.tls_host if tls else '[::1]' if host=='::1' else '127.0.0.1'
        url=f'{scheme}://{probe_host}:{port}/api/health'
        context=ssl._create_unverified_context() if tls else None
        try:
            with direct_open(url,.8,context) as response:
                if response.status!=200:return False
                payload=json.loads(response.read().decode('utf-8'))
                return isinstance(payload,dict) and payload.get('status')=='ok' and payload.get('phase')==6
        except (OSError,ValueError,TypeError,KeyError,URLError):
            return False
    def start(role,host,port,tls=False):
        stop=control/(uuid.uuid4().hex+'.stop')
        command=[str(python),str(ROOT/'scripts/serve_app.py'),'--role',role,'--host',host,'--port',str(port),'--shutdown-file',str(stop)]
        if tls:command+=['--ssl-certfile',str(args.ssl_certfile.resolve()),'--ssl-keyfile',str(args.ssl_keyfile.resolve())]
        if args.behind_proxy and role=='private':command+=['--trusted-proxy']
        output=control/(stop.stem+f'.{role}.stderr.log')
        # Never inherit a terminal/pipe that can disappear with the launcher.
        # Keep import/configuration errors too (before rotating application logging starts).
        with output.open('wb') as log:
            output.chmod(0o600)
            child=subprocess.Popen(command,cwd=ROOT/'backend',env=env,stdin=subprocess.DEVNULL,
                                   stdout=log,stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        children.append((child,stop,role))
        startup_logs[role]=output
        owned.add(child)
        return child
    def startup_error(child,reason):
        output=startup_logs['private']
        with output.open('rb') as log:
            log.seek(max(0,output.stat().st_size-12000))
            tail=log.read().decode('utf-8',errors='replace')
        for name in ('ADMIN_PASSWORD','BOOTH_PAIRING_KEY'):
            if env.get(name):tail=tail.replace(env[name],'[redacted]')
        return RuntimeError(f'{reason}; backend exit code={child.poll()}. Captured stdout/stderr: {output}\n{tail}')
    try:
        tls=args.profile=='https' and not args.behind_proxy
        child=start('private',bind,args.port,tls)
        scheme='https' if tls else 'http';probe_host=args.tls_host if tls else '[::1]' if bind=='::1' else '127.0.0.1';probe=f'{scheme}://{probe_host}:{args.port}/api/health'
        context=ssl.create_default_context() if tls else None
        if tls:context.load_verify_locations(cafile=str(args.ssl_certfile))
        for _ in range(150):
            if child.poll() is not None:
                if existing_photobooth(bind,args.port,tls):
                    raise RuntimeError(f'Photobooth is already running on port {args.port}. Stop that instance before starting another one.')
                raise startup_error(child,f'Host backend exited before readiness on port {args.port}')
            try:
                with direct_open(probe,1,context) as response:
                    payload=json.load(response)
                    if response.status==200 and isinstance(payload,dict) and payload.get('status')=='ok' and payload.get('phase')==6 and payload.get('startup_id')==startup_id:break
            except (OSError,ValueError):time.sleep(.2)
        else:raise startup_error(child,'Host direct localhost health check timed out (process may still be running)')
        if args.public_gateway:start('public','127.0.0.1',args.public_port)
        save_drive_setting(env,env['OSA_STORAGE_ROOT'])
        print('Google Drive: '+('enabled (background upload)' if env.get('GOOGLE_DRIVE_ENABLED','false').lower()=='true' else 'disabled (local storage only)'),flush=True)
        manifest.write_text(json.dumps({'launcher_pid':os.getpid(),'profile':args.profile,'port':args.port,'children':[{'pid':p.pid,'role':r,'stop_file':str(s)} for p,s,r in children]},indent=2),encoding='utf-8')
        print(f'Private listener: {bind}:{args.port} ({args.profile})',flush=True)
        if args.behind_proxy:
            print('Open the configured private HTTPS reverse-proxy URL for /booth, /admin and /event-display; HTTP upstream is not a browser login URL.',flush=True)
            gallery_url='/gallery on the configured HTTPS origin'
        else:
            private_host=args.lan_ip if args.profile=='lan' else args.tls_host if tls else 'localhost'
            print(f'Host Dashboard (laptop only): {scheme}://localhost:{args.port}/admin',flush=True)
            print(f'Event display (separate Host-issued code): {scheme}://{private_host}:{args.port}/event-display',flush=True)
            gallery_url=f'{scheme}://{private_host}:{args.port}/gallery'
        gallery_status='enabled' if env_flag('PUBLIC_GALLERY_ENABLED') else 'disabled; set PUBLIC_GALLERY_ENABLED=true and restart'
        print(f'Photo Gallery: {gallery_url} ({gallery_status})',flush=True)
        print(f'Camera: {args.camera}; Printer: {args.printer}. Mock never means hardware verified.',flush=True)
        if not args.behind_proxy:
            print(f'Booth: {scheme}://{private_host}:{args.port}/booth',flush=True)
            if args.profile=='lan':print(f'Booth on laptop: http://localhost:{args.port}/booth',flush=True)
        print('Ctrl+C or python scripts/stop_host.py to stop. No public tunnel was started.',flush=True)
        network_check=time.monotonic()+10
        while all(p.poll() is None for p,_,_ in children):
            time.sleep(.3)
            if args.profile=='lan' and auto_lan and time.monotonic()>=network_check:
                network_check=time.monotonic()+10
                try:current_ip=detect_lan_ipv4()
                except (OSError,ValueError):continue
                if current_ip!=args.lan_ip:
                    args.lan_ip=current_ip
                    print(f'LAN address changed. Open http://{current_ip}:{args.port}/booth on iPad. The listener remains active; no second server was started. Existing public QR configuration is unchanged.',flush=True)
        if not any(stop.exists() for _,stop,_ in children):
            raise RuntimeError('A service stopped unexpectedly; all owned services are stopping. Inspect logs before restarting.')
    except KeyboardInterrupt:pass
    finally:
        for process,stop,_ in children:
            if process.poll() is None:stop.write_text('stop',encoding='utf-8')
        for process,_,role in children:
            try:process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                print(f'{role} did not stop within 30 seconds; terminating owned process. Check any uncertain camera/print job before retry.',flush=True)
                # On Windows the venv python.exe is a wrapper: terminate the owned
                # job too, otherwise its real interpreter retains runtime leases.
                if os.name=='nt':owned.close()
                else:process.terminate()
                process.wait(timeout=10)
        owned.close()
        for _,stop,_ in children:stop.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True);lease.close()
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (RuntimeError,ValueError,OSError,subprocess.CalledProcessError) as error:raise SystemExit(str(error))
