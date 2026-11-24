"""Safely abandon one failed Sony capture or preserve an unmatched buffer with the Host stopped.

First record abandonment. Then attest that the camera is physically unpowered
and the old media removed, and verify a fresh PTP session after power-on.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT))
from app.runtime_lock import RuntimeLock
from app.services.camera.base import CameraError
from app.services.camera.sony_ptp import SonyPtpDriver, UNCLAIMED_BUFFER
from scripts.diagnose_sony_camera import probe_windows


def cancel(storage, capture_id, *, confirm_discard, timeout=15, isolation_step=None, preserve_buffer=False):
    if not preserve_buffer and not confirm_discard:raise RuntimeError('Add --confirm-discard only after deciding to abandon this failed capture.')
    if (isolation_step or preserve_buffer) and not capture_id:raise RuntimeError('Camera recovery requires the full --capture-id.')
    if preserve_buffer and (isolation_step or confirm_discard):raise RuntimeError('Preserving an unmatched buffer is a separate action from discarding a capture.')
    storage=Path(storage).resolve()
    if not (storage/'photobooth.sqlite3').is_file():raise RuntimeError('Existing Host database was not found; check --storage-root. Nothing was changed.')
    try:lease=RuntimeLock(storage/'.host-app.lock').acquire()
    except RuntimeError:raise RuntimeError('Stop the Photobooth Host in Terminal 1 first; no process was killed.') from None
    driver=None;camera_lease=None
    try:
        try:camera_lease=RuntimeLock(storage/'.camera-controller.lock').acquire()
        except RuntimeError:raise RuntimeError('A camera controller still owns this runtime. Stop its Host first; no process was killed.') from None
        root=storage/'camera_originals/sony-recovery'
        if capture_id is None:
            candidates=[p for p in root.glob('*.json') if json.loads(p.read_text(encoding='utf-8')).get('status') not in ('saved','cancelled','superseded')]
            if not candidates:return {'status':'no_pending_capture'}
            if len(candidates)!=1:raise RuntimeError(f'Found {len(candidates)} unresolved receipts. Specify the intended --capture-id; nothing was changed.')
            capture_id=candidates[0].stem
        capture_id=str(uuid.UUID(capture_id))
        database=storage/'photobooth.sqlite3'
        # mode=rw refuses to invent a fresh database or run migrations.
        with sqlite3.connect(database.as_uri()+'?mode=rw',uri=True,timeout=5) as db:
            db.row_factory=sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM camera_captures WHERE status IN ('capturing','transferring') LIMIT 1").fetchone():
                raise RuntimeError('A capture is still active in the Host database; no abandonment was recorded.')
            row=db.execute('SELECT * FROM camera_captures WHERE id=?',(capture_id,)).fetchone()
            if not row or row['adapter_mode']!='sony_zve10':raise RuntimeError('No matching Sony Host capture; nothing was changed.')
            if row['status']=='captured' or row['native_path'] or row['photo_id']:raise RuntimeError('This capture has a saved original; abandonment was refused.')
            if row['status'] not in ('failed','transfer_failed'):raise RuntimeError('Capture is still active; stop and inspect it before cancellation.')
            if row['error_code']=='capture_cancelled':return {'status':'already_cancelled'}
            if (root.parent/str(uuid.UUID(row['session_id']))/(capture_id+'.jpg')).is_file():
                raise RuntimeError('An original exists for this capture; preserve it and reconcile its identity first.')
            journal=root/f'{capture_id}.json'
            decision=root/'cancelled'/journal.name
            if journal.is_file() and decision.is_file():
                original=journal.read_bytes()
                if decision.read_bytes()==original and json.loads(original).get('status')=='cancelled':
                    return {'status':'already_cancelled'}
            if isolation_step or preserve_buffer:
                pnp=probe_windows(timeout)
                if pnp['status']!='QUERIED':
                    raise RuntimeError('Cannot verify Windows PnP state. The capture remains blocked.')
                devices=pnp['devices']
                if isolation_step=='power_off' and devices:
                    raise RuntimeError('Windows still sees a Sony device. Disconnect the Sony USB cable, battery and external power.')
                if isolation_step=='verify_reconnect' or preserve_buffer:
                    healthy=[item for item in devices if item['original_zv_e10_name_match'] and item['pnp_status']=='OK']
                    if len(healthy)!=1 or any(item['pnp_status']!='OK' for item in devices):
                        raise RuntimeError('Expected one healthy Sony ZV-E10 in Windows. Check Device Manager before opening WIA.')
            driver=SonyPtpDriver(storage,timeout)
            if isolation_step!='power_off':driver.connect()
            if preserve_buffer:
                def blocked_before_shutter(item):
                    return (item['status']=='failed' and item['error_code']=='camera_recovery_pending'
                            and item['error_message']==UNCLAIMED_BUFFER and not item['adapter_reference']
                            and not item['native_path'] and not item['photo_id']
                            and not (root/(item['id']+'.json')).exists())
                unclaimed_preflight=blocked_before_shutter(row)
                other=db.execute("""SELECT * FROM camera_captures WHERE adapter_mode='sony_zve10' AND id!=?
                    AND uncertain=1 AND status!='captured' AND COALESCE(error_code,'') NOT IN ('capture_cancelled','capture_superseded')""",(capture_id,))
                if any(not blocked_before_shutter(item) for item in other):
                    raise RuntimeError('Another Sony capture is unresolved. Use the original recovery for it first.')
                known_hashes={}
                for other in db.execute('SELECT id,native_sha256 FROM camera_captures WHERE native_sha256 IS NOT NULL'):
                    known_hashes.setdefault(other['native_sha256'],set()).add(other['id'])
                for path in root.glob('*.json'):
                    record=json.loads(path.read_bytes())
                    for digest in (record.get('sha256'),record.get('received_sha256')):
                        if digest:known_hashes.setdefault(digest,set()).add(path.stem)
                result=driver.preserve_unassigned_buffer(capture_id,time.monotonic()+timeout,known_hashes=known_hashes,
                                                        unclaimed_preflight=unclaimed_preflight)
                if unclaimed_preflight and result['buffer_drained']:
                    db.execute("""UPDATE camera_captures SET error_code='capture_cancelled', uncertain=0,
                        error_message='No shutter sent. Unassigned JPEG preserved separately.',
                        updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""",(capture_id,))
                return result
            receipt=driver.cancel_capture(capture_id,time.monotonic()+timeout,confirm_discard=True,isolation_step=isolation_step)
            if isolation_step=='verify_reconnect' and receipt.get('isolation_verified_at'):
                return {'status':'abandonment_isolated','physical_outcome':'uncertain','file_info':'0x0000',
                        'receipt_archive':str(root/'cancelled'/f'{capture_id}.json'),
                        'next_step':'Start Host and connect camera from a new session to reconcile into SQLite.',
                        'shutter_sent':False,'photos_deleted':False}
            if receipt['status']=='cancelled':
                return {'status':'already_cancelled'}
            if isolation_step=='power_off':
                return {'status':'power_off_recorded','physical_outcome':'uncertain','new_capture_blocked':True,
                        'power_off_at':receipt['isolation_power_off_at'],'photos_deleted':False}
            return {'status':'abandonment_pending','receipt_archive':str(root/'abandonment'/f'{capture_id}.json'),
                    'physical_outcome':'uncertain','file_info':'0x0000','new_capture_blocked':True,
                    'shutter_sent':False,'photos_deleted':False}
    finally:
        try:
            if driver is not None:driver.disconnect()
        finally:
            if camera_lease is not None:camera_lease.close()
            lease.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root',type=Path,default=ROOT/'runtime')
    parser.add_argument('--capture-id',type=str)
    parser.add_argument('--confirm-discard',action='store_true')
    isolation=parser.add_mutually_exclusive_group()
    isolation.add_argument('--record-power-off',dest='isolation_step',action='store_const',const='power_off',
        help='Attest USB, battery and other power are physically disconnected and old memory card is removed now.')
    isolation.add_argument('--verify-reconnect',dest='isolation_step',action='store_const',const='verify_reconnect',
        help='Attest the same camera is now powered on with the old card still out and no shot taken since restart.')
    isolation.add_argument('--preserve-buffer',action='store_true',
        help='Save one observed unmatched Sony JPEG to private recovery storage without assigning it to a session.')
    parser.add_argument('--timeout',type=float,default=15)
    args=parser.parse_args()
    if not 1<=args.timeout<=60:parser.error('--timeout must be 1-60 seconds')
    try:print(json.dumps(cancel(args.storage_root,args.capture_id,confirm_discard=args.confirm_discard,
        timeout=args.timeout,isolation_step=args.isolation_step,preserve_buffer=args.preserve_buffer),indent=2))
    except (RuntimeError,CameraError,KeyError,ValueError,OSError,sqlite3.Error) as error:
        print(str(error),file=sys.stderr);return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
