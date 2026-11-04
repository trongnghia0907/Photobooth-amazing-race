"""Sony diagnostics. Default: PnP only. --connect-preview opens real WIA/PTP.

--capture requires --confirm-shutter and --output-dir. Stop the Host first;
the transport ownership mutex also prevents concurrent diagnostic/Host access.
No camera images are deleted and no hardware verification flag is granted.
"""
import argparse
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import hashlib
from io import BytesIO
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.camera.sony_zve10 import SonyZvE10CameraAdapter
from app.services.camera.base import CameraError


PNP_QUERY=r"""$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$candidates=@(Get-PnpDevice -PresentOnly -ErrorAction Stop |
    Where-Object { $_.FriendlyName -match 'Sony|ZV-E10' } |
    Select-Object -First 32 Status,Class,FriendlyName)
ConvertTo-Json -InputObject @($candidates) -Depth 3 -Compress
"""


def probe_windows(timeout=15):
    if platform.system()!='Windows':
        return {'status':'UNSUPPORTED','detail':'This PnP check requires Windows.','devices':[]}
    powershell=shutil.which('powershell.exe')
    if not powershell:
        return {'status':'UNAVAILABLE','detail':'Windows PowerShell was not found. Use Device Manager to inspect the camera.','devices':[]}
    try:
        result=subprocess.run([powershell,'-NoLogo','-NoProfile','-NonInteractive','-Command',PNP_QUERY],
            capture_output=True,text=True,encoding='utf-8-sig',timeout=timeout,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=False)
    except subprocess.TimeoutExpired:
        return {'status':'TIMEOUT','detail':'Windows PnP query timed out; camera presence is unknown.','devices':[]}
    except (OSError,UnicodeError):
        return {'status':'UNAVAILABLE','detail':'Could not read Windows PnP devices; camera presence is unknown.','devices':[]}
    if result.returncode:
        return {'status':'UNAVAILABLE','detail':'Windows rejected the read-only PnP query. Check Device Manager; this is not proof the camera is absent.',
                'exit_code':result.returncode,'devices':[]}
    try:
        rows=json.loads(result.stdout)
        if not isinstance(rows,list) or not all(isinstance(row,dict) for row in rows):raise ValueError()
    except (ValueError,TypeError):
        return {'status':'UNAVAILABLE','detail':'Unexpected PnP response; camera presence is unknown.','devices':[]}
    devices=[]
    for row in rows[:32]:
        # Deliberately omit device instance IDs, serials and all other properties.
        name=str(row.get('FriendlyName') or '')[:160]
        devices.append({'name':name,'class':str(row.get('Class') or '')[:80],
                        'pnp_status':str(row.get('Status') or '')[:40],
                        'original_zv_e10_name_match':bool(re.fullmatch(r'(?:Sony\s+)?ZV-E10',name.strip(),re.I))})
    return {'status':'QUERIED','devices':devices,
            'detail':'PnP names only. A matching name does not verify PC Remote, Live View, shutter or original JPEG transfer.'}


def diagnostic(timeout=15, *, connect_preview=False, capture=False, output_dir=None):
    adapter=SonyZvE10CameraAdapter(timeout=timeout)
    state=adapter.get_status()
    result={'adapter':'sony_zve10','configured_model':'ZV-E10 (first generation)',
            'mode':'READ_ONLY','camera_access':'NOT_OPENED','pnp':probe_windows(timeout),
            'integration_available':state['integration_available'],
            'blocker':state.get('blocker'),
            'capabilities':adapter.get_capabilities().json(),
            'protocol_checks':{name:'NOT_TESTED' for name in ('usb_ptp_session','live_view','physical_shutter','original_jpeg')},
            'physical_hardware_verification':'NOT_TESTED',
            'verdict':'NOT_TESTED - use --connect-preview to test USB/PTP without firing the shutter'}
    if not connect_preview and not capture:return result
    if capture and not output_dir:raise ValueError('Capture requires an explicit output directory')
    # Do not read runtime configuration, photos or OAuth credentials.
    with tempfile.TemporaryDirectory(prefix='photobooth-sony-check-') as temporary:
        adapter=SonyZvE10CameraAdapter(storage_root=Path(output_dir) if capture else Path(temporary),timeout=timeout)
        result.update(mode='CONFIRMED_PHYSICAL_CAPTURE' if capture else 'READ_ONLY_PTP',camera_access='OPENING')
        check='usb_ptp_session'
        try:
            adapter.connect()
            result['camera_access']='OPENED'
            result['protocol_checks'][check]='PASS'
            result['identified_model']=adapter.get_status()['model']
            check='live_view'
            adapter.start_live_view()
            preview_deadline=time.monotonic()+timeout
            while True:
                try:
                    frame=adapter.get_preview_frame()
                    break
                except CameraError as error:
                    if error.code not in ('not_ready','busy','preview_pending') or time.monotonic()>=preview_deadline:raise
                    time.sleep(min(0.1,max(0,preview_deadline-time.monotonic())))
            result['protocol_checks'][check]='PASS'
            result['preview_bytes']=len(frame.data)
            if capture:
                identifier=str(uuid.uuid4());check='physical_shutter'
                end=time.monotonic()+timeout
                reference=adapter.capture_photo(identifier,end)
                # A command ACK is not proof of a successful physical photo.
                result['protocol_checks'][check]='NOT_TESTED'
                check='original_jpeg'
                photo=adapter.get_captured_photo(reference,end)
                result['protocol_checks']['physical_shutter']='PASS'
                result['protocol_checks'][check]='PASS'
                result['jpeg_bytes']=len(photo.data)
                result['jpeg_sha256']=hashlib.sha256(photo.data).hexdigest()
                with Image.open(BytesIO(photo.data)) as original:
                    result['jpeg_dimensions']={'width':original.width,'height':original.height}
                result['saved_test_image']=str(adapter.driver._paths(identifier)[1].resolve())
                result['physical_hardware_verification']='DIAGNOSTIC_ONLY - full 4/6 workflow still needs testing'
            result['verdict']='PASS - requested device checks completed; hardware_verified remains false'
        except CameraError as error:
            result['protocol_checks'][check]='FAIL'
            result['error']={'code':error.code,'message':str(error),'uncertain':error.uncertain}
            result['verdict']='FAIL - check USB data cable, PC Remote/USB, camera mode; close Imaging Edge and stop Host before diagnostics'
        finally:
            adapter.disconnect()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout',type=float,default=15,help='PnP query timeout in seconds (1-60); never triggers capture')
    parser.add_argument('--connect-preview',action='store_true',help='Open WIA/PTP, identify model and read Live View; no shutter')
    parser.add_argument('--capture',action='store_true',help='Test one physical shutter and save its original JPEG')
    parser.add_argument('--confirm-shutter',action='store_true',help='Explicitly authorize one physical shutter for --capture')
    parser.add_argument('--output-dir',type=Path,help='Private recovery directory for the one test JPEG')
    args=parser.parse_args()
    if not 1<=args.timeout<=60:parser.error('--timeout must be between 1 and 60 seconds')
    if args.capture and not (args.confirm_shutter and args.output_dir):
        parser.error('--capture requires --confirm-shutter and --output-dir; this physically fires the camera')
    result=diagnostic(args.timeout,connect_preview=args.connect_preview,capture=args.capture,output_dir=args.output_dir)
    print(json.dumps(result,indent=2,ensure_ascii=True))
    return 0 if result['verdict'].startswith('PASS') else 2


if __name__=='__main__':raise SystemExit(main())
