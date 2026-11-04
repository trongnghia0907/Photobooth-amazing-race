"""CLI/PnP stubs only: no Sony USB/PTP commands or physical hardware checks."""
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest

spec=importlib.util.spec_from_file_location('sony_diagnostic',Path(__file__).resolve().parents[2]/'scripts/diagnose_sony_camera.py')
diagnostic=importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(diagnostic.platform,'system',lambda:'Windows')
    monkeypatch.setattr(diagnostic.shutil,'which',lambda _: 'powershell.exe')


def test_readonly_query_does_not_report_name_as_a_working_driver(windows,monkeypatch):
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        return SimpleNamespace(returncode=0,stdout=json.dumps([
            {'FriendlyName':'Sony ZV-E10','Status':'OK','Class':'WPD','InstanceId':'DO-NOT-EXPOSE'},
            {'FriendlyName':'ZV-E10M2','Status':'OK','Class':'Camera'}]))
    monkeypatch.setattr(diagnostic.subprocess,'run',run)
    # If diagnostics ever start accessing a device, fail the test immediately.
    for method in ['connect','capture_photo','start_live_view','get_captured_photo']:
        monkeypatch.setattr(diagnostic.SonyZvE10CameraAdapter,method,lambda *args:pytest.fail('Device access forbidden'))
    result=diagnostic.diagnostic(7)
    assert result['pnp']['devices'][0]['original_zv_e10_name_match']
    assert not result['pnp']['devices'][1]['original_zv_e10_name_match']
    assert result['camera_access']=='NOT_OPENED' and result['integration_available']
    assert result['physical_hardware_verification']=='NOT_TESTED'
    assert set(result['protocol_checks'].values())=={'NOT_TESTED'}
    assert 'DO-NOT-EXPOSE' not in json.dumps(result)
    assert calls[0][1]['timeout']==7
    assert 'Get-PnpDevice -PresentOnly' in calls[0][0][-1]


@pytest.mark.parametrize('response,expected',[
    (SimpleNamespace(returncode=0,stdout='[]'),'QUERIED'),
    (SimpleNamespace(returncode=1,stdout='internal-secret'),'UNAVAILABLE'),
    (SimpleNamespace(returncode=0,stdout='invalid-json'),'UNAVAILABLE'),
    (SimpleNamespace(returncode=0,stdout='{}'),'UNAVAILABLE'),
])
def test_missing_device_errors_and_bad_results_are_distinct(windows,monkeypatch,response,expected):
    monkeypatch.setattr(diagnostic.subprocess,'run',lambda *args,**kwargs:response)
    result=diagnostic.probe_windows()
    assert result['status']==expected and not result['devices']
    assert 'internal-secret' not in json.dumps(result)


def test_timeout_is_not_camera_absence(windows,monkeypatch):
    def run(*args,**kwargs):raise subprocess.TimeoutExpired('powershell',1)
    monkeypatch.setattr(diagnostic.subprocess,'run',run)
    assert diagnostic.probe_windows()['status']=='TIMEOUT'


def test_unsupported_platform_and_missing_powershell_do_not_spawn(windows,monkeypatch):
    monkeypatch.setattr(diagnostic.subprocess,'run',lambda *args,**kwargs:pytest.fail('Unexpected process'))
    monkeypatch.setattr(diagnostic.platform,'system',lambda:'Linux')
    assert diagnostic.probe_windows()['status']=='UNSUPPORTED'
    monkeypatch.setattr(diagnostic.platform,'system',lambda:'Windows')
    monkeypatch.setattr(diagnostic.shutil,'which',lambda _:None)
    assert diagnostic.probe_windows()['status']=='UNAVAILABLE'


def test_cli_reports_blocked_with_nonzero_exit_without_device_access(monkeypatch,capsys):
    monkeypatch.setattr(diagnostic.sys,'argv',['diagnose_sony_camera.py'])
    monkeypatch.setattr(diagnostic,'probe_windows',lambda timeout:{'status':'QUERIED','devices':[]})
    assert diagnostic.main()==2
    result=json.loads(capsys.readouterr().out)
    assert result['verdict'].startswith('NOT_TESTED') and result['camera_access']=='NOT_OPENED'


def test_readonly_ptp_checks_live_view_without_firing_shutter(tmp_path,monkeypatch):
    from test_sony_ptp import FakeWia
    from app.services.camera.sony_zve10 import SonyZvE10CameraAdapter
    wire=FakeWia()
    def adapter(**kwargs):
        result=SonyZvE10CameraAdapter(**kwargs);result.driver.transport=wire;return result
    monkeypatch.setattr(diagnostic,'SonyZvE10CameraAdapter',adapter)
    monkeypatch.setattr(diagnostic,'probe_windows',lambda timeout:{'status':'QUERIED','devices':[]})
    result=diagnostic.diagnostic(connect_preview=True)
    assert result['protocol_checks']=={'usb_ptp_session':'PASS','live_view':'PASS','physical_shutter':'NOT_TESTED','original_jpeg':'NOT_TESTED'}
    assert wire.shots==0 and not wire.connected and result['physical_hardware_verification']=='NOT_TESTED'


def test_explicit_capture_uses_real_driver_and_keeps_the_original(tmp_path,monkeypatch):
    from test_sony_ptp import FakeWia
    from app.services.camera.sony_zve10 import SonyZvE10CameraAdapter
    wire=FakeWia()
    def adapter(**kwargs):
        result=SonyZvE10CameraAdapter(**kwargs);result.driver.transport=wire;return result
    monkeypatch.setattr(diagnostic,'SonyZvE10CameraAdapter',adapter)
    monkeypatch.setattr(diagnostic,'probe_windows',lambda timeout:{'status':'QUERIED','devices':[]})
    result=diagnostic.diagnostic(capture=True,output_dir=tmp_path)
    assert set(result['protocol_checks'].values())=={'PASS'}
    assert Path(result['saved_test_image']).is_file() and wire.shots==1 and not wire.connected
    assert result['jpeg_dimensions']=={'width':320,'height':240} and len(result['jpeg_sha256'])==64
    assert not result['capabilities']['hardware_verified']


def test_cli_requires_explicit_physical_shutter_confirmation(monkeypatch):
    monkeypatch.setattr(diagnostic.sys,'argv',['diagnose_sony_camera.py','--capture'])
    monkeypatch.setattr(diagnostic,'diagnostic',lambda *args,**kwargs:pytest.fail('Must not open camera'))
    with pytest.raises(SystemExit) as caught:diagnostic.main()
    assert caught.value.code==2


def test_diagnostic_waits_for_documented_temporary_live_view_not_ready(tmp_path,monkeypatch):
    from test_sony_ptp import FakeWia
    from app.services.camera.sony_zve10 import SonyZvE10CameraAdapter
    wire=FakeWia();command=wire.command;reads=0
    def warming(operation,*args,**kwargs):
        nonlocal reads
        if operation==0x9209:
            reads+=1;wire.live=int(reads>=3)
        return command(operation,*args,**kwargs)
    wire.command=warming
    def adapter(**kwargs):
        result=SonyZvE10CameraAdapter(**kwargs);result.driver.transport=wire;return result
    monkeypatch.setattr(diagnostic,'SonyZvE10CameraAdapter',adapter)
    monkeypatch.setattr(diagnostic,'probe_windows',lambda timeout:{'status':'QUERIED','devices':[]})
    result=diagnostic.diagnostic(timeout=2,connect_preview=True)
    assert result['protocol_checks']['live_view']=='PASS' and wire.open_count==1 and wire.shots==0
