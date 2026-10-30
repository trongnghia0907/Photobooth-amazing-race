"""Offline backup restores the same photo links and durable queue, without overwrite."""
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.public_main import create_public_app
from test_sharing import finalized
from test_printing import enqueue,wait_job


def test_offline_backup_restore_keeps_images_tokens_and_queue(tmp_path):
    settings=Settings(tmp_path/'source',public_base_url='http://localhost:8000',app_env='development')
    with TestClient(create_app(settings)) as client:
        a,_,one=finalized(client,'red');b,_,two=finalized(client,'blue')
        before=[client.get(s['share']['download_url']).content for s in [one,two]]
        job=enqueue(client,a,one,2).json()
        assert wait_job(client,a,job['id'])['status']=='submitted'
    target=tmp_path/'backup';root=Path(__file__).resolve().parents[2]
    command=[sys.executable,str(root/'scripts/backup_runtime.py'),'--storage-root',str(settings.storage_root),'--output',str(target)]
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    result=subprocess.run(command,capture_output=True,timeout=30,**flags)
    assert result.returncode==0,result.stderr
    manifest=json.loads((target/'backup-manifest.json').read_text(encoding='utf-8'))
    assert '.share-key' in manifest and 'photobooth.sqlite3' in manifest
    for relative,digest in manifest.items():
        assert hashlib.sha256((target/relative).read_bytes()).hexdigest()==digest
        assert hashlib.sha256((settings.storage_root/relative).read_bytes()).hexdigest()==digest
    assert subprocess.run(command,capture_output=True,timeout=10,**flags).returncode!=0
    restored=replace(settings,storage_root=target)
    with TestClient(create_public_app(restored)) as public:
        after=[public.get(s['share']['download_url']).content for s in [one,two]]
        assert after==before and before[0]!=before[1]
        with public.app.state.repository.db.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM session_finals').fetchone()[0]==2
            row=db.execute('SELECT status,copies FROM print_jobs WHERE id=?',(job['id'],)).fetchone()
            assert tuple(row)==('submitted',2)
