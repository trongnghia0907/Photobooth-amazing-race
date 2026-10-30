"""Supervised single-worker server; stop-file requests graceful Uvicorn shutdown."""
import argparse
from pathlib import Path
import sys
import threading

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
parser=argparse.ArgumentParser()
parser.add_argument('--role',choices=['private','public'],required=True)
parser.add_argument('--host',default='127.0.0.1')
parser.add_argument('--port',type=int,required=True)
parser.add_argument('--shutdown-file',type=Path,required=True)
parser.add_argument('--ssl-certfile')
parser.add_argument('--ssl-keyfile')
parser.add_argument('--trusted-proxy',action='store_true')
args=parser.parse_args()
import uvicorn
config=uvicorn.Config('app.main:app' if args.role=='private' else 'app.public_main:app',
    host=args.host,port=args.port,workers=1,proxy_headers=args.trusted_proxy,
    forwarded_allow_ips='127.0.0.1',ssl_certfile=args.ssl_certfile,ssl_keyfile=args.ssl_keyfile)
server=uvicorn.Server(config)
done=threading.Event()
def monitor():
    while not done.wait(.2):
        if args.shutdown_file.is_file():server.should_exit=True;return
watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
try:server.run()
finally:done.set()
