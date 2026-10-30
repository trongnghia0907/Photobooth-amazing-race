"""Real Uvicorn process restart acceptance test, with isolated disk storage."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

import httpx

from test_sessions import headers, key, image


def test_uvicorn_process_restart_preserves_completed_session(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    root = tmp_path/'restart-storage'
    env = {**os.environ, 'OSA_STORAGE_ROOT':str(root), 'PUBLIC_BASE_URL':'https://photos.osa.test', 'PRINTER_MODE':'mock','ENABLE_PHYSICAL_PRINTING':'false'}
    backend = Path(__file__).resolve().parents[1]
    client = httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=10)

    def start():
        process = subprocess.Popen(
            [sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],
            cwd=backend,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError('Uvicorn failed to start')
            try:
                if client.get('/api/health').status_code == 200:
                    return process
            except httpx.TransportError:
                pass
            time.sleep(.1)
        process.terminate()
        process.wait(timeout=10)
        raise AssertionError('Uvicorn startup timed out')

    def stop(process):
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)

    process = start()
    try:
        sid=client.post('/api/sessions',headers=headers(key()),json={'layout':'grid2x3','slot_count':6}).json()['session_id']
        for slot in range(6):
            response=client.post(f'/api/sessions/{sid}/photos',headers=headers(key()),data={'slot_index':slot,'source':'demo'},files={'file':('shot.png',image(),'image/png')})
            assert response.status_code == 200,response.text
        response=client.put(f'/api/sessions/{sid}/composite',headers=headers(key()),data={'shots_revision':6},files={'file':('final.png',image('red'),'image/png')})
        assert response.status_code == 200,response.text
        final=response.json()['composite']['id']
        complete_key=key()
        completed=client.post(f'/api/sessions/{sid}/complete',headers=headers(complete_key),json={'composite_id':final})
        assert completed.status_code == 200,completed.text
        assert completed.json()['status'] == 'completed'
        shared=client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json={'composite_id':final})
        assert shared.status_code==200,shared.text
        from urllib.parse import urlsplit
        share_path=urlsplit(shared.json()['share']['share_url']).path
        image_before=client.get(share_path+'/image').content
    finally:
        stop(process)
    process=start()
    try:
        restored=client.get(f'/api/sessions/{sid}',headers=headers())
        assert restored.json() == shared.json()
        assert client.post(f'/api/sessions/{sid}/complete',headers=headers(complete_key),json={'composite_id':final}).json() == completed.json()
        assert len(list(root.rglob('*.png'))) == 3  # official composite, QR, print-ready; working shots cleaned
        assert client.get(share_path+'/image').content==image_before
        assert client.get(share_path+'/download').status_code==200
        assert client.get(f'/api/sessions/{sid}/composites/{final}/image',headers=headers()).status_code == 200
    finally:
        stop(process)
        client.close()
