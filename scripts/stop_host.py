"""Stop only the supervised instance described in the private runtime manifest."""
import argparse
import json
import os
from pathlib import Path
import re
import time

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--storage-root',type=Path,default=Path(os.environ.get('OSA_STORAGE_ROOT',root/'runtime')))
args=parser.parse_args()
storage=args.storage_root.expanduser().resolve();manifest=storage/'.operator-run.json'
if not manifest.is_file():raise SystemExit('No supervised instance manifest. Stop manually launched Uvicorn with Ctrl+C.')
data=json.loads(manifest.read_text(encoding='utf-8'));control=(storage/'.run-control').resolve()
for child in data['children']:
    target=Path(child['stop_file']).resolve()
    if target.parent!=control or not control.is_relative_to(storage) or not re.fullmatch(r'[0-9a-f]{32}\.stop',target.name):
        raise SystemExit('Invalid stop manifest; refusing to write outside the runtime control directory')
    target.write_text('stop',encoding='utf-8')
for _ in range(170):
    if not manifest.exists():print('Stopped supervised OSA services.');break
    time.sleep(.2)
else:raise SystemExit('Shutdown still pending. Inspect the launcher terminal; do not start another instance or retry an uncertain print.')
