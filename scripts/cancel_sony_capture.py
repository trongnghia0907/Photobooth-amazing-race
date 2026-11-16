"""Cancel ONE explicitly abandoned empty Sony capture, with the Host stopped.

Keeps an exact receipt archive, checks the camera buffer, never sends a shutter,
and never deletes images. Credentials, Drive and public sharing are untouched.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.runtime_lock import RuntimeLock
from app.services.camera.base import CameraError
from app.services.camera.sony_ptp import SonyPtpDriver


def cancel(storage, capture_id, *, confirm_discard, timeout=15):
    if not confirm_discard:raise RuntimeError('Add --confirm-discard only after deciding to abandon this failed capture.')
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
            candidates=[p for p in root.glob('*.json') if json.loads(p.read_text(encoding='utf-8')).get('status') not in ('saved','cancelled')]
            if not candidates:return {'status':'no_pending_capture'}
            if len(candidates)!=1:raise RuntimeError(f'Found {len(candidates)} unresolved receipts. Specify the intended --capture-id; nothing was changed.')
            capture_id=candidates[0].stem
        capture_id=str(uuid.UUID(capture_id))
        database=storage/'photobooth.sqlite3'
        # mode=rw refuses to invent a fresh database or run migrations.
        with sqlite3.connect(database.as_uri()+'?mode=rw',uri=True,timeout=5) as db:
            db.row_factory=sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM camera_captures WHERE id=?',(capture_id,)).fetchone()
            if not row or row['adapter_mode']!='sony_zve10':raise RuntimeError('No matching Sony Host capture; nothing was changed.')
            if row['status']=='captured' or row['native_path']:raise RuntimeError('This capture has a saved original; cancellation was refused.')
            if row['status'] not in ('failed','transfer_failed'):raise RuntimeError('Capture is still active; stop and inspect it before cancellation.')
            if row['error_code']=='capture_cancelled':return {'status':'already_cancelled'}
            driver=SonyPtpDriver(storage,timeout)
            driver.connect()
            driver.cancel_capture(capture_id,time.monotonic()+timeout,confirm_discard=True)
            db.execute("UPDATE camera_captures SET status='failed',error_code='capture_cancelled',error_message=?,uncertain=0,updated_at=? WHERE id=?",
                ('Operator cancelled an unresolved capture; original files retained.',datetime.now(timezone.utc).isoformat(),capture_id))
            db.commit()
            return {'status':'cancelled','receipt_archive':str(root/'cancelled'/f'{capture_id}.json'),'shutter_sent':False,'photos_deleted':False}
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
    parser.add_argument('--timeout',type=float,default=15)
    args=parser.parse_args()
    if not 1<=args.timeout<=60:parser.error('--timeout must be 1-60 seconds')
    try:print(json.dumps(cancel(args.storage_root,args.capture_id,confirm_discard=args.confirm_discard,timeout=args.timeout),indent=2))
    except (RuntimeError,CameraError,ValueError,OSError,sqlite3.Error) as error:
        print(str(error),file=sys.stderr);return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
