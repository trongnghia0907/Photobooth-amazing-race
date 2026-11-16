"""Windows spawn must import the Host entrypoint without launching Uvicorn."""
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
import os
import subprocess
import pytest


def test_wia_spawn_import_never_restarts_host(monkeypatch):
    root=Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root/'scripts'))
    monkeypatch.setattr(sys,'argv',['serve_app.py','--role','private','--port','8000','--shutdown-file','unused.stop'])
    def forbidden(*args,**kwargs):raise AssertionError('WIA spawn imported and restarted Host')
    monkeypatch.setitem(sys.modules,'uvicorn',SimpleNamespace(Config=forbidden))
    monkeypatch.setitem(sys.modules,'owned_processes',SimpleNamespace(join_owned_job=lambda:None))
    runpy.run_path(str(root/'scripts/serve_app.py'),run_name='__mp_main__')


@pytest.mark.skipif(os.name!='nt',reason='Windows spawn entrypoint regression')
def test_real_supervised_entrypoint_can_spawn_a_child(tmp_path):
    root=Path(__file__).resolve().parents[2]
    # Only Uvicorn is replaced. Run the actual launcher entrypoint in a fresh
    # interpreter, then spawn a real child exactly as the WIA transport does.
    (tmp_path/'uvicorn.py').write_text('''import multiprocessing as mp
def reply(channel):
    channel.send('spawn-ok');channel.close()
class Config:
    def __init__(self,*args,**kwargs):pass
class Server:
    def __init__(self,config):self.started=False
    def run(self):
        ctx=mp.get_context('spawn');parent,child=ctx.Pipe()
        process=ctx.Process(target=reply,args=(child,))
        try:
            process.start();child.close()
            assert parent.poll(10), 'WIA-style child failed during Host import'
            assert parent.recv()=='spawn-ok'
            process.join(5);assert process.exitcode==0
            self.started=True;print('spawn-ok')
        finally:
            if process.is_alive():process.terminate();process.join(5)
            parent.close();process.close()
''',encoding='utf-8')
    env={**os.environ,'PYTHONPATH':str(tmp_path),'APP_ENV':'development','OPERATION_MODE':'development',
         'OSA_STORAGE_ROOT':str(tmp_path/'storage'),'OSA_LOG_DIRECTORY':str(tmp_path/'logs'),
         'GOOGLE_DRIVE_ENABLED':'false','CAMERA_ADAPTER':'mock','PRINTER_MODE':'mock','PUBLIC_BASE_URL':'http://localhost:8000'}
    result=subprocess.run([sys.executable,str(root/'scripts/serve_app.py'),'--role','private','--port','8000',
        '--shutdown-file',str(tmp_path/'stop')],env=env,cwd=root,capture_output=True,text=True,timeout=25)
    assert result.returncode==0,result.stderr
    assert 'spawn-ok' in result.stdout
