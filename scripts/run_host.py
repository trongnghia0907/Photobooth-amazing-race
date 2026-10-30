"""Windows-first same-origin host launcher. Never starts a public tunnel."""
import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.runtime_lock import RuntimeLock


def main():
    parser=argparse.ArgumentParser(description='Run built OSA kiosk + API without Vite')
    parser.add_argument('--profile',choices=['local','lan','https'],default='local')
    parser.add_argument('--storage-root',type=Path,default=Path(os.environ.get('OSA_STORAGE_ROOT',ROOT/'runtime')))
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--bind')
    parser.add_argument('--lan-ip')
    parser.add_argument('--public-url')
    parser.add_argument('--public-gateway',action='store_true',help='Start photo-only gateway on loopback; does not expose Internet')
    parser.add_argument('--public-port',type=int,default=8001)
    parser.add_argument('--camera',choices=['mock','vendor','uvc_demo'],default='mock')
    parser.add_argument('--printer',choices=['mock','windows'],default='mock')
    parser.add_argument('--enable-physical-printing',action='store_true')
    parser.add_argument('--ssl-certfile',type=Path)
    parser.add_argument('--ssl-keyfile',type=Path)
    parser.add_argument('--tls-host',default='localhost',help='Private HTTPS hostname/IP matching the certificate, for health check and operator URL')
    parser.add_argument('--behind-proxy',action='store_true')
    parser.add_argument('--build',action='store_true')
    parser.add_argument('--no-prompt',action='store_true')
    args=parser.parse_args()
    if not args.tls_host or any(c in args.tls_host for c in '/:@ \t\r\n'):parser.error('--tls-host must be a hostname or IPv4 without scheme/port')
    if not 1<=args.port<=65535 or not 1<=args.public_port<=65535 or args.public_port==args.port:parser.error('Invalid/distinct ports required')
    python=ROOT/'backend/.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.is_file():parser.error('Create backend/.venv and install requirements.lock.txt first')
    if args.build:
        npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm')
        if not npm:parser.error('Install Node/npm first')
        subprocess.run([npm,'run','build:host'],cwd=ROOT/'frontend',check=True)
    dist=ROOT/'frontend/dist-host'
    if not (dist/'index.html').is_file():parser.error('Run cd frontend; npm.cmd ci; npm.cmd run build:host (or --build)')
    env={**os.environ,'OSA_STORAGE_ROOT':str(args.storage_root.expanduser().resolve()),'OSA_FRONTEND_DIST':str(dist),
         'CAMERA_ADAPTER':args.camera,'CAMERA_GUEST_ENABLED':'true','CAMERA_ALLOW_FAULTS':'false',
         'PRINTER_MODE':args.printer,'ENABLE_PHYSICAL_PRINTING':'true' if args.enable_physical_printing else 'false',
         'ALLOW_LAN_HTTP':'false'}
    def credential(name,prompt,minimum):
        value=env.get(name,'')
        if not value and not args.no_prompt:value=getpass.getpass(prompt) if 'PASSWORD' in name or 'KEY' in name else input(prompt).strip()
        if len(value)<minimum:parser.error(f'{name} needs at least {minimum} characters; use environment or interactive prompt')
        env[name]=value
    credential('ADMIN_USERNAME','Host username: ',1)
    credential('ADMIN_PASSWORD','Host password (12+ characters, hidden): ',12)
    credential('BOOTH_PAIRING_KEY','Kiosk pairing code (16+ characters, hidden): ',16)
    if args.profile=='lan':
        try:
            address=ipaddress.ip_address(args.lan_ip or '')
            valid=address.version==4 and any(address in ipaddress.ip_network(net) for net in ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'])
        except ValueError:valid=False
        if not valid:parser.error('--lan-ip must be the laptop RFC1918 IPv4 from ipconfig')
        bind=args.bind or '0.0.0.0';env.update(APP_ENV='development',ALLOW_LAN_HTTP='true',PUBLIC_BASE_URL=f'http://{address}:{args.port}')
    elif args.profile=='https':
        origin=args.public_url or env.get('PUBLIC_BASE_URL','')
        if not origin.startswith('https://'):parser.error('--public-url HTTPS origin required')
        bind=args.bind or '127.0.0.1';env.update(APP_ENV='production',PUBLIC_BASE_URL=origin)
        if args.behind_proxy:
            if bind not in ('127.0.0.1','::1'):parser.error('Behind-proxy origin must bind loopback')
        elif not (args.ssl_certfile and args.ssl_keyfile and args.ssl_certfile.is_file() and args.ssl_keyfile.is_file()):
            parser.error('HTTPS needs --ssl-certfile and --ssl-keyfile, or an explicitly configured --behind-proxy on loopback')
    else:
        bind=args.bind or '127.0.0.1'
        if bind!='127.0.0.1':parser.error('Local profile uses 127.0.0.1; use --profile lan explicitly for LAN exposure')
        env.update(APP_ENV='development',PUBLIC_BASE_URL=f'http://localhost:{args.port}')
    # Validate config without printing sensitive values.
    validated=subprocess.run([str(python),'-c','from app.config import Settings; from app.services.sharing import public_origin; s=Settings.from_environment(); public_origin(s.public_base_url,allow_local=s.app_env=="development",allow_lan=s.allow_lan_http)'],cwd=ROOT/'backend',env=env)
    if validated.returncode:return validated.returncode
    storage=Path(env['OSA_STORAGE_ROOT']);storage.mkdir(parents=True,exist_ok=True)
    lease=RuntimeLock(storage/'.launcher.lock').acquire()
    control=storage/'.run-control';control.mkdir(exist_ok=True)
    manifest=storage/'.operator-run.json';children=[]
    def start(role,host,port,tls=False):
        stop=control/(uuid.uuid4().hex+'.stop')
        command=[str(python),str(ROOT/'scripts/serve_app.py'),'--role',role,'--host',host,'--port',str(port),'--shutdown-file',str(stop)]
        if tls:command+=['--ssl-certfile',str(args.ssl_certfile.resolve()),'--ssl-keyfile',str(args.ssl_keyfile.resolve())]
        if args.behind_proxy and role=='private':command+=['--trusted-proxy']
        child=subprocess.Popen(command,cwd=ROOT/'backend',env=env,stdin=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        children.append((child,stop,role))
        return child
    try:
        tls=args.profile=='https' and not args.behind_proxy
        child=start('private',bind,args.port,tls)
        scheme='https' if tls else 'http';probe_host=args.tls_host if tls else '[::1]' if bind=='::1' else '127.0.0.1';probe=f'{scheme}://{probe_host}:{args.port}/api/health'
        context=ssl.create_default_context() if tls else None
        if tls:context.load_verify_locations(cafile=str(args.ssl_certfile))
        for _ in range(150):
            if child.poll() is not None:raise RuntimeError('Host server failed to start; see configuration/logs')
            try:
                with urllib.request.urlopen(probe,timeout=1,context=context) as response:
                    if response.status==200:break
            except (OSError,ValueError):time.sleep(.2)
        else:raise RuntimeError('Host health check timed out')
        if args.public_gateway:start('public','127.0.0.1',args.public_port)
        manifest.write_text(json.dumps({'profile':args.profile,'port':args.port,'children':[{'pid':p.pid,'role':r,'stop_file':str(s)} for p,s,r in children]},indent=2),encoding='utf-8')
        if args.behind_proxy:
            print('Open the configured private HTTPS reverse-proxy URL for /booth, /admin and /event-display; HTTP upstream is not a browser login URL.',flush=True)
        else:
            private_host=args.lan_ip if args.profile=='lan' else args.tls_host if tls else 'localhost'
            print(f'Booth: {scheme}://{private_host}:{args.port}/booth',flush=True)
            print(f'Host Dashboard (laptop only): {scheme}://localhost:{args.port}/admin',flush=True)
            print(f'Event display (separate Host-issued code): {scheme}://{private_host}:{args.port}/event-display',flush=True)
        print(f'Camera: {args.camera}; Printer: {args.printer}. Mock never means hardware verified.',flush=True)
        print('Ctrl+C or python scripts/stop_host.py to stop. No public tunnel was started.',flush=True)
        while all(p.poll() is None for p,_,_ in children):time.sleep(.3)
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
                process.terminate();process.wait(timeout=10)
        for _,stop,_ in children:stop.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True);lease.close()
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (RuntimeError,subprocess.CalledProcessError) as error:raise SystemExit(str(error))
