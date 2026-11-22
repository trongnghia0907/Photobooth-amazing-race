"""Verify a saved Sony acceptance-test capture without opening the camera."""

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.camera.base import CameraError
from app.services.camera.sony_ptp import check_jpeg


def verify_original(data, receipt, native_sha256):
    """Decode the primary image with the same JPEG/MPO validator as the Host."""
    dimensions = check_jpeg(data)
    sha256 = hashlib.sha256(data).hexdigest()
    if sha256 != native_sha256 or sha256 != receipt.get('sha256') or sha256 != receipt.get('received_sha256'):
        raise ValueError('Original SHA-256 differs from SQLite or the Sony receipt.')
    if len(data) != receipt['object']['size'] or list(dimensions) != receipt.get('jpeg_dimensions'):
        raise ValueError('Original byte count or primary image dimensions differ from the Sony receipt.')
    return {'jpeg_dimensions': list(dimensions), 'jpeg_bytes': len(data), 'sha256': sha256}


def verify_saved_capture(storage_root, session_id, capture_id, slot_index):
    storage = Path(storage_root).resolve()
    session_id, capture_id = str(UUID(session_id)), str(UUID(capture_id))
    expected_path = f'camera_originals/{session_id}/{capture_id}.jpg'
    database = (storage / 'photobooth.sqlite3').as_uri() + '?mode=ro'
    with sqlite3.connect(database, uri=True) as db:
        db.row_factory = sqlite3.Row
        row = db.execute('''SELECT c.native_path, c.native_sha256, c.photo_id, p.width, p.height FROM camera_captures c
            JOIN slots s ON s.session_id=c.session_id AND s.slot_index=c.slot_index AND s.photo_id=c.photo_id
            JOIN photos p ON p.id=s.photo_id AND p.session_id=s.session_id AND p.slot_index=s.slot_index
            WHERE c.id=? AND c.session_id=? AND c.slot_index=? AND c.adapter_mode='sony_zve10'
            AND c.status='captured' AND c.uncertain=0 AND c.error_code IS NULL
            AND c.mime='image/jpeg' AND p.source='camera_original' ''', (capture_id, session_id, slot_index)).fetchone()
    if row is None or row['native_path'] != expected_path:
        raise ValueError('The requested session and slot do not hold this saved Sony original.')

    journal = storage / 'camera_originals' / 'sony-recovery' / f'{capture_id}.json'
    receipt = json.loads(journal.read_bytes())
    if (receipt.get('status') != 'saved' or receipt.get('buffer_drained') is not True
            or receipt.get('last_buffer_value') != 0 or receipt.get('release_pending') is not False
            or receipt.get('half_release_pending') is not False):
        raise ValueError('The Sony receipt does not confirm a saved original, released shutter and empty buffer.')
    original = verify_original((storage / expected_path).read_bytes(), receipt, row['native_sha256'])
    if sorted(original['jpeg_dimensions']) != sorted((row['width'], row['height'])):
        raise ValueError('Original dimensions differ from the saved slot after accounting for orientation.')
    return {**original, 'capture_id': capture_id, 'photo_id': row['photo_id'], 'slot': slot_index + 1,
            'native_path': expected_path, 'camera_object': receipt['object'].get('name'),
            'file_info': '0x0000', 'receipt_status': receipt['status']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, default=ROOT / 'runtime')
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--capture-id', required=True)
    parser.add_argument('--slot', type=int, choices=range(1, 7), required=True, help='Booth slot number (1 through 6).')
    args = parser.parse_args()
    try:
        result = verify_saved_capture(args.storage_root, args.session_id, args.capture_id, args.slot - 1)
    except (CameraError, KeyError, OSError, ValueError, sqlite3.Error) as error:
        parser.exit(2, f'{error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
