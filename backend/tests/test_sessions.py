from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import json
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.services import repository as repository_module


TOKEN = 'a' * 64


def headers(key=None, token=TOKEN):
    result = {'Authorization': f'Bearer {token}'}
    if key:
        result['Idempotency-Key'] = key
    return result


def key():
    return str(uuid.uuid4())


def image(color='blue', size=(80, 60)):
    output = BytesIO()
    Image.new('RGB', size, color).save(output, 'PNG')
    return output.getvalue()


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path / 'storage', max_upload_bytes=100_000, max_image_pixels=2_000_000)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def create(client, operation=None, **body):
    result = client.post('/api/sessions', headers=headers(operation or key()), json={'layout': 'grid2x3', 'slot_count': 6, **body})
    assert result.status_code == 200, result.text
    return result.json()['session_id']


def upload(client, sid, slot, operation=None, payload=None, source='demo', filename='fixture.png'):
    return client.post(f'/api/sessions/{sid}/photos', headers=headers(operation or key()),
                       data={'slot_index': slot, 'source': source},
                       files={'file': (filename, payload or image(), 'image/png')})


def composite(client, sid, revision, operation=None, payload=None):
    return client.put(f'/api/sessions/{sid}/composite', headers=headers(operation or key()),
                      data={'shots_revision': revision, 'editor_json': '{"filter":"normal"}'},
                      files={'file': ('final.png', payload or image('green'), 'image/png')})


def six_photos(client, sid):
    for slot in range(6):
        response = upload(client, sid, slot)
        assert response.status_code == 200, response.text
    return response.json()


def test_complete_workflow_retake_files_sqlite_and_restart(client, settings):
    assert client.get('/api/health').json()['status'] == 'ok'
    sid = create(client)
    state = six_photos(client, sid)
    assert state['status'] == 'editing'
    old_photo = state['photos'][1]['id']
    state = upload(client, sid, 1, payload=image('red'), source='webcam_frame').json()
    assert state['photos'][1]['revision'] == 2
    assert state['photos'][1]['source'] == 'webcam_frame'
    assert state['photos'][1]['id'] != old_photo
    state = composite(client, sid, state['shots_revision']).json()
    final = state['composite']
    complete_key = key()
    response = client.post(f'/api/sessions/{sid}/complete', headers=headers(complete_key), json={'composite_id': final['id']})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'completed'
    assert client.post(f'/api/sessions/{sid}/complete', headers=headers(complete_key), json={'composite_id': final['id']}).json() == response.json()
    with sqlite3.connect(settings.storage_root/'photobooth.sqlite3') as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 8
        assert db.execute('SELECT COUNT(*) FROM photos').fetchone()[0] == 7
        paths = [r[0] for r in db.execute('SELECT path FROM photos UNION ALL SELECT path FROM composites')]
        assert all((settings.storage_root/p).is_file() == p.startswith('composites/') for p in paths)
        assert all(not Path(p).is_absolute() for p in paths)
    # New application/repository instances reopen the same DB/files, not RAM.
    with TestClient(create_app(settings)) as restarted:
        persisted = restarted.get(f'/api/sessions/{sid}', headers=headers()).json()
        assert persisted == response.json()
        photo_url = f'/api/sessions/{sid}/photos/{persisted["photos"][1]["id"]}/image'
        assert restarted.get(photo_url, headers=headers()).status_code == 410
        assert restarted.get(photo_url).status_code == 401
        final_url = f'/api/sessions/{sid}/composites/{final["id"]}/image'
        downloaded = restarted.get(final_url, headers=headers())
        assert downloaded.status_code == 200
        assert downloaded.headers['cache-control'] == 'no-store'
        assert Image.open(BytesIO(downloaded.content)).size == (80, 60)


def test_create_and_upload_retry_are_idempotent(client, settings):
    create_key = key()
    sid = create(client, create_key)
    assert create(client, create_key) == sid
    conflict = client.post('/api/sessions', headers=headers(create_key), json={'layout': 'grid3x2', 'slot_count': 6})
    assert conflict.status_code == 409
    upload_key = key()
    original = upload(client, sid, 0, upload_key).json()
    assert upload(client, sid, 0, upload_key).json() == original
    assert upload(client, sid, 0, upload_key, image('red')).status_code == 409
    with sqlite3.connect(settings.storage_root/'photobooth.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM photos').fetchone()[0] == 1
    assert len(list(settings.storage_root.rglob('*.png'))) == 1


def test_parallel_retries_create_one_session(client, settings):
    operation = key()
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: create(client, operation), range(4)))
    assert len(set(ids)) == 1


def test_access_validation_and_no_public_gallery(client):
    sid = create(client)
    for path in ['/api/sessions', '/gallery', '/runtime', '/api/photos']:
        assert client.get(path).status_code in (404, 405)
    assert client.get(f'/api/sessions/{sid}').status_code == 401
    assert client.get(f'/api/sessions/{sid}', headers=headers(token='b'*64)).status_code == 404
    assert client.get(f'/api/sessions/{uuid.uuid4()}', headers=headers()).status_code == 404
    assert client.get('/api/sessions/not-a-uuid', headers=headers()).status_code == 422
    assert upload(client, sid, 6).status_code == 422
    assert upload(client, sid, -1).status_code == 422
    assert upload(client, sid, 0, source='physical_shutter').status_code == 422
    assert client.post('/api/sessions', json={}, headers=headers()).status_code == 422
    # Foreign photo cannot be accessed with another session's credential.
    photo = upload(client, sid, 0).json()['photos'][0]['id']
    another = create(client)
    assert client.get(f'/api/sessions/{another}/photos/{photo}/image', headers=headers()).status_code == 404


def test_invalid_files_limits_and_filename_traversal(client, settings):
    sid = create(client)
    assert upload(client, sid, 0, payload=b'not an image').status_code == 422
    bad_type = client.post(f'/api/sessions/{sid}/photos', headers=headers(key()), data={'slot_index':0,'source':'demo'}, files={'file':('x.svg',b'<svg/>','image/svg+xml')})
    assert bad_type.status_code == 415
    assert upload(client, sid, 0, payload=b'x' * 100_001).status_code == 413
    assert upload(client, sid, 0, payload=image(size=(2000,2000))).status_code == 413
    assert upload(client, sid, 0, filename='../../outside.png').status_code == 200
    assert not (settings.storage_root.parent/'outside.png').exists()
    assert all(p.parent.name == sid for p in settings.storage_root.rglob('*.png'))


def test_storage_failure_does_not_claim_success_or_replace_old_slot(client, settings, monkeypatch):
    sid = create(client)
    old = upload(client, sid, 0).json()
    operation = key()
    actual_write = repository_module.atomic_write
    def broken(*args):
        raise OSError('disk full')
    monkeypatch.setattr(repository_module, 'atomic_write', broken)
    failed = upload(client, sid, 0, operation, image('red'))
    assert failed.status_code == 503
    assert 'disk full' not in failed.text
    assert client.get(f'/api/sessions/{sid}', headers=headers()).json() == old
    assert not list(settings.storage_root.rglob('*.tmp'))
    monkeypatch.setattr(repository_module, 'atomic_write', actual_write)
    recovered = upload(client, sid, 0, operation, image('red')).json()
    assert recovered['photos'][0]['revision'] == 2
    assert recovered['photos'][0]['id'] != old['photos'][0]['id']


def test_composite_requires_all_current_shots_and_retry_stable(client, settings):
    sid = create(client)
    assert composite(client, sid, 0).status_code == 409
    state = six_photos(client, sid)
    assert composite(client, sid, state['shots_revision']-1).status_code == 409
    operation = key()
    state = composite(client, sid, state['shots_revision'], operation).json()
    assert composite(client, sid, state['shots_revision'], operation).json() == state
    image_id = state['composite']['id']
    upload(client, sid, 4, payload=image('purple'))
    assert client.post(f'/api/sessions/{sid}/complete', headers=headers(key()), json={'composite_id':image_id}).status_code == 409
    assert len(list((settings.storage_root/'composites').rglob('*.png'))) == 1


def test_deletion_reset_and_four_slot_backend(client):
    sid = create(client)
    six_photos(client, sid)
    operation = key()
    state = client.delete(f'/api/sessions/{sid}/photos/1',headers=headers(operation)).json()
    assert len(state['photos']) == 5
    assert client.delete(f'/api/sessions/{sid}/photos/1',headers=headers(operation)).json() == state
    assert client.delete(f'/api/sessions/{sid}/photos',headers=headers(key())).json()['photos'] == []
    four = create(client, layout='landscape_4', slot_count=4)
    for index in range(4):
        assert upload(client, four, index).status_code == 200
    assert upload(client, four, 4).status_code == 422
    assert client.get(f'/api/sessions/{four}',headers=headers()).json()['status'] == 'editing'


def test_complete_detects_missing_disk_file(client, settings):
    sid = create(client)
    state = six_photos(client, sid)
    state = composite(client, sid, state['shots_revision']).json()
    next((settings.storage_root/'composites').rglob('*.png')).unlink()
    response = client.post(f'/api/sessions/{sid}/complete',headers=headers(key()),json={'composite_id':state['composite']['id']})
    assert response.status_code == 409
    assert client.get(f'/api/sessions/{sid}',headers=headers()).json()['status'] == 'failed'


def test_request_body_limit_including_chunked(client):
    sid = create(client)
    oversized = b'x' * 200_000
    response = client.post(f'/api/sessions/{sid}/photos',headers={**headers(key()),'Content-Type':'application/octet-stream'},content=oversized)
    assert response.status_code == 413
    prefix = b'--test-boundary\r\nContent-Disposition: form-data; name="file"; filename="large.png"\r\nContent-Type: image/png\r\n\r\n'
    response = client.post(f'/api/sessions/{sid}/photos',headers={**headers(key()),'Content-Type':'multipart/form-data; boundary=test-boundary'},
                           content=iter([prefix,oversized[:100000],oversized[100000:],b'\r\n--test-boundary--\r\n']))
    assert response.status_code == 413


def test_database_failure_rolls_back_new_file_and_metadata(client, settings, monkeypatch):
    sid = create(client)
    repo = client.app.state.repository
    original_snapshot = repo.snapshot
    def broken(*args):
        raise sqlite3.OperationalError('injected commit preparation failure')
    monkeypatch.setattr(repo, 'snapshot', broken)
    # Upload's authorization uses get/snapshot, so exercise the transactional
    # repository directly after image validation instead of failing preflight.
    from app.services.images import ValidatedImage
    data = image()
    with pytest.raises(sqlite3.OperationalError):
        repo.upload_photo(sid,TOKEN,key(),0,'demo',ValidatedImage(data,80,60,'test-sha','test-input'))
    monkeypatch.setattr(repo, 'snapshot', original_snapshot)
    assert not list(settings.storage_root.rglob('*.png'))
    assert client.get(f'/api/sessions/{sid}',headers=headers()).json()['photos'] == []


def test_mock_printer_is_dry_run_only(tmp_path):
    from app.services.mock_printer import MockPrinterAdapter
    original=tmp_path/'fixture.png'
    original.write_bytes(image())
    job=uuid.uuid4().hex
    result=MockPrinterAdapter(tmp_path/'mock-print').preview(original,job)
    assert result['mode'] == 'mock' and result['printed'] is False
    assert (tmp_path/'mock-print'/f'{job}.png').read_bytes() == original.read_bytes()
    with pytest.raises(ValueError):
        MockPrinterAdapter(tmp_path/'mock-print').preview(original,'../../unsafe')
