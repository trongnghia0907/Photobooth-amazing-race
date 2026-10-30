"""Offline verified copy; never deletes or overwrites source/user photo data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'backend'))
from app.runtime_lock import RuntimeLock
parser=argparse.ArgumentParser()
parser.add_argument('--storage-root',type=Path,default=Path(os.environ.get('OSA_STORAGE_ROOT',root/'runtime')))
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();source=args.storage_root.expanduser().resolve();output=args.output.expanduser().resolve()
if not (source/'photobooth.sqlite3').is_file():raise SystemExit('No source database')
if output==source or output.is_relative_to(source) or output.exists():raise SystemExit('Use a new backup directory outside the source runtime')
leases=[]
try:
    for name in ('.launcher.lock','.host-app.lock','.public-app.lock','.print-worker.lock','.camera-controller.lock'):
        leases.append(RuntimeLock(source/name).acquire())
    output.mkdir(parents=True);hashes={}
    for path in source.rglob('*'):
        if path.resolve()!=path or not path.resolve().is_relative_to(source):raise RuntimeError('Backup refuses symlinks/junctions outside canonical storage paths')
        if not path.is_file() or path.name.endswith('.lock') or '.run-control' in path.parts or path.name=='.operator-run.json':continue
        relative=path.relative_to(source);target=output/relative;target.parent.mkdir(parents=True,exist_ok=True)
        expected=hashlib.sha256(path.read_bytes()).hexdigest();shutil.copy2(path,target)
        actual=hashlib.sha256(target.read_bytes()).hexdigest()
        if actual!=expected:raise RuntimeError('Backup checksum mismatch; keep source and do not restore this incomplete copy')
        hashes[relative.as_posix()]=actual
    (output/'backup-manifest.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print(f'Offline backup verified: {len(hashes)} files. Protect the backup: it includes private photos and .share-key.')
finally:
    for lease in reversed(leases):lease.close()
