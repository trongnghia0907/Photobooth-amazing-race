from dataclasses import replace
import importlib.util
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.services import cups_printer
from app.services.printers import PrinterError
from app.services.camera.base import CameraCapabilities
from test_sessions import create,upload,headers,key


def test_environment_fails_closed_and_requires_explicit_rehearsal(monkeypatch,tmp_path):
    monkeypatch.setenv('APP_ENV','production');monkeypatch.setenv('OSA_STORAGE_ROOT',str(tmp_path))
    monkeypatch.delenv('OPERATION_MODE',raising=False);monkeypatch.delenv('ALLOW_MOCK_HARDWARE',raising=False)
    config=Settings.from_environment()
    assert config.operation_mode=='event' and not config.demo_hardware_allowed
    monkeypatch.setenv('OPERATION_MODE','development')
    with pytest.raises(ValueError,match='Production requires'):Settings.from_environment()
    monkeypatch.setenv('OPERATION_MODE','rehearsal')
    with pytest.raises(ValueError,match='explicit'):Settings.from_environment()
    monkeypatch.setenv('ALLOW_MOCK_HARDWARE','true')
    assert Settings.from_environment().demo_hardware_allowed
    monkeypatch.setenv('ENABLE_PHYSICAL_PRINTING','tru')
    with pytest.raises(ValueError,match='true or false'):Settings.from_environment()
    with pytest.raises(ValueError):replace(config,app_env='developmnt')
    with pytest.raises(ValueError):replace(config,camera_allow_faults=True)


def test_event_rejects_mock_and_unverified_hardware_without_a_shutter(tmp_path,monkeypatch):
    settings=Settings(tmp_path,operation_mode='event',camera_guest_enabled=True)
    with TestClient(create_app(settings)) as client:
        sid=create(client);camera=client.app.state.camera
        result=client.post(f'/api/sessions/{sid}/camera/connect',headers=headers())
        assert result.status_code==503 and result.json()['error']['code']=='event_hardware_required'
        assert camera.adapter.shutter_calls==0
        assert upload(client,sid,0).status_code==403
        monkeypatch.setattr(camera.adapter,'get_capabilities',lambda:CameraCapabilities('sdk','Unverified SDK',False,True,True,True,True,'camera_original'))
        assert client.post(f'/api/sessions/{sid}/camera/connect',headers=headers()).status_code==503
        assert camera.adapter.shutter_calls==0 and not client.app.state.printing.config()['available']
        config=client.get('/api/booth/config').json()
        assert config['event_mode'] and not config['mock_hardware_allowed']
        assert set(config)=={'operation_mode','event_mode','mock_hardware_allowed','guest_idle_seconds','gallery_poll_seconds','recent_gallery_available'}
        assert client.get('/api/admin/status').status_code==401


def test_low_disk_preserves_old_photo_and_blocks_shutter_before_capture(tmp_path,monkeypatch):
    from app.services import repository
    settings=Settings(tmp_path,app_env='development',camera_guest_enabled=True)
    with TestClient(create_app(settings)) as client:
        sid=create(client);saved=upload(client,sid,0).json()['photos'][0]['id']
        assert client.post(f'/api/sessions/{sid}/camera/connect',headers=headers()).status_code==200
        monkeypatch.setattr(repository.shutil,'disk_usage',lambda path:SimpleNamespace(free=1))
        assert upload(client,sid,0).status_code==507
        assert client.post(f'/api/sessions/{sid}/camera/captures',headers=headers(key()),json={'slot_index':1}).status_code==507
        assert client.app.state.camera.adapter.shutter_calls==0
        assert client.get(f'/api/sessions/{sid}',headers=headers()).json()['photos'][0]['id']==saved
        assert client.get(f'/api/sessions/{sid}/photos/{saved}/image',headers=headers()).status_code==200


def test_environment_file_precedence_paths_and_no_shell_execution(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('host_environment',Path(__file__).resolve().parents[2]/'scripts/host_environment.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    config=tmp_path/'event.env';config.write_text('HOST_PORT=9123\nOSA_STORAGE_ROOT=../photos\nCAMERA_MODEL="$(do-not-execute)"\n',encoding='utf-8')
    monkeypatch.setenv('HOST_PORT','9234');monkeypatch.delenv('OSA_STORAGE_ROOT',raising=False)
    env=module.load_environment(config)
    assert env['HOST_PORT']=='9234' and env['OSA_STORAGE_ROOT']==str((tmp_path/'../photos').resolve())
    assert env['CAMERA_MODEL']=='$(do-not-execute)'
    config.write_text('ADMIN_PASSWORD=private\nADMIN_PASSWORD=other\n')
    with pytest.raises(ValueError,match='Duplicate configuration variable ADMIN_PASSWORD'):module.load_environment(config)


def test_cups_discovery_submission_and_uncertain_timeout_use_fake_processes(tmp_path,monkeypatch):
    monkeypatch.setattr(cups_printer.sys,'platform','darwin')
    monkeypatch.setattr(cups_printer.shutil,'which',lambda command:'/usr/bin/'+command)
    calls=[]
    def run(command,**kwargs):
        assert kwargs['timeout']==5 and kwargs['env']['LC_ALL']=='C' and 'shell' not in kwargs
        calls.append(command)
        if command[0].endswith('lpstat'):
            output='printer Photo is idle. enabled since today\nprinter Offline disabled since today\n' if '-p' in command else 'Photo accepting requests since today\nOffline not accepting requests\n'
        else:output='request id is Photo-17 (1 file(s))'
        return SimpleNamespace(stdout=output)
    monkeypatch.setattr(cups_printer.subprocess,'run',run)
    adapter=cups_printer.CupsPrinterAdapter()
    with pytest.raises(PrinterError):adapter.print_image(tmp_path/'image.png',2,{'printer_id':'Photo','job_id':'test'})
    assert not calls
    adapter.enabled=True
    assert [item['id'] for item in adapter.list_printers()]==['Photo']
    receipt=adapter.print_image(tmp_path/'image.png',2,{'printer_id':'Photo','job_id':'test'})
    assert receipt['spooler_job_id']=='Photo-17' and not receipt['physical_print_confirmed']
    sent=[call for call in calls if call[0].endswith('/lp')]
    assert len(sent)==1 and sent[0][1:5]==['-d','Photo','-n','2'] and sent[0][-2]=='--'
    def timeout(command,**kwargs):
        if command[0].endswith('/lp'):raise subprocess.TimeoutExpired(command,5)
        return run(command,**kwargs)
    monkeypatch.setattr(cups_printer.subprocess,'run',timeout)
    with pytest.raises(PrinterError) as error:adapter.print_image(tmp_path/'image.png',1,{'printer_id':'Photo','job_id':'other'})
    assert error.value.uncertain
    monkeypatch.setattr(cups_printer.sys,'platform','win32')
    assert 'requires macOS/Linux' in adapter.diagnostic() and adapter.list_printers()==[]


def test_log_redaction_preserves_access_formatter_and_numeric_arguments():
    import logging
    from app.logging_filters import ShareTokenFilter
    scrub=ShareTokenFilter()
    access=logging.LogRecord('uvicorn.access',logging.INFO,'',0,'%s - "%s %s HTTP/%s" %d',('client','GET','/p/secret-token/image','1.1',200),None)
    assert scrub.filter(access) and len(access.args)==5 and 'secret-token' not in access.getMessage()
    ordinary=logging.LogRecord('app',logging.INFO,'',0,'%s %s %d',('a','b',3),None)
    scrub.filter(ordinary);assert ordinary.getMessage()=='a b 3'


def test_host_frame_management_is_authenticated_and_persistent(tmp_path):
    settings=Settings(tmp_path/'frames',app_env='development',public_base_url='http://localhost:8000',admin_username='frame-host',admin_password='frame-password-123')
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/admin/frames').status_code==401
        login=client.post('/api/admin/login',headers={'X-OSA-Login':'1'},json={'username':settings.admin_username,'password':settings.admin_password})
        assert login.status_code==200
        csrf=login.json()['csrf_token']
        presets=client.get('/api/admin/frames');assert presets.status_code==200 and len(presets.json()['items'])==3
        saved=client.put('/api/admin/frames/custom',headers={'X-CSRF-Token':csrf},json={'name':'Host frame','layout':'grid2x3','slot_count':6,'pad_x':6,'pad_top':7,'pad_bottom':15,'gap':3,'slots':[],'enabled':True})
        assert saved.status_code==200
        with client.app.state.repository.db.connect() as db:
            assert db.execute("SELECT value FROM host_settings WHERE key='frame:custom'").fetchone()


def test_launcher_loads_config_from_another_cwd_and_check_starts_nothing(tmp_path):
    import os,secrets,sys
    root=Path(__file__).resolve().parents[2]
    values={'APP_ENV':'development','OPERATION_MODE':'rehearsal','ALLOW_MOCK_HARDWARE':'true','HOST_PROFILE':'local',
            'ADMIN_USERNAME':'preflight-test','ADMIN_PASSWORD':secrets.token_urlsafe(24),'BOOTH_PAIRING_KEY':secrets.token_urlsafe(24),
            'OSA_STORAGE_ROOT':'runtime','PHOTOBOOTH_PYTHON':sys.executable,'PUBLIC_BASE_URL':'http://localhost:8000',
            'CAMERA_ADAPTER':'mock','PRINTER_MODE':'mock','ENABLE_PHYSICAL_PRINTING':'false'}
    config=tmp_path/'operator.env';config.write_text('\n'.join(f'{k}={v}' for k,v in values.items()),encoding='utf-8')
    env={k:v for k,v in os.environ.items() if k not in values}
    command=[sys.executable,str(root/'scripts/run_host.py'),'--env-file',str(config),'--check','--no-prompt']
    result=subprocess.run(command,cwd=tmp_path,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert 'Configuration valid: rehearsal' in result.stdout
    assert not (tmp_path/'runtime').exists()
    values['APP_ENV']='production'
    config.write_text('\n'.join(f'{k}={v}' for k,v in values.items()),encoding='utf-8')
    result=subprocess.run(command,cwd=tmp_path,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode!=0 and 'refusing to silently change environment' in result.stderr
