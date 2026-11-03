"""Read-only localhost/runtime startup evidence. Never prints credentials."""
import json
from pathlib import Path
import sqlite3
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.runtime_lock import RuntimeLock
storage=ROOT/'runtime'
for name in ('.launcher.lock','.host-app.lock','.print-worker.lock','.camera-controller.lock'):
    try:
        lease=RuntimeLock(storage/name).acquire();lease.close();print(name,'AVAILABLE')
    except RuntimeError:print(name,'HELD')
try:
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8000/api/health',timeout=2) as response:
        body=json.load(response);print('DIRECT HEALTH',response.status,body.get('status'),body.get('phase'))
except Exception as error:print('DIRECT HEALTH',type(error).__name__,str(error))
with sqlite3.connect((storage/'photobooth.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
    print('DATABASE',json.dumps({'version':db.execute('PRAGMA user_version').fetchone()[0],
        'credential_rows':db.execute('SELECT COUNT(*) FROM admin_credentials').fetchone()[0],
        'kiosk_auth_tag_count':db.execute('SELECT COUNT(DISTINCT auth_tag) FROM booth_stations').fetchone()[0],
        'session_count':db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]}))
