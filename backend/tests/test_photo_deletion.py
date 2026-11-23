from dataclasses import replace
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.services.drive_client import DriveError, GoogleDriveClient
from app.services.repository import Repository
from test_drive_storage import FakeDrive
from test_event_display import approve
from test_photo_gallery import publish, settings
from test_printing import login
from test_sessions import headers, key


def test_delete_one_final_and_revoke_all_local_routes(settings):
    with TestClient(create_app(settings)) as client:
        repo = client.app.state.repository
        repo.cloud.stop()
        assert client.delete('/api/admin/sessions/00000000-0000-4000-8000-000000000001/'
                             'composites/00000000-0000-4000-8000-000000000002').status_code == 401
        csrf = login(client, settings)
        sid, display, share = publish(client, csrf)
        other_sid, other_display, other_share = publish(client, csrf)
        with repo.db.connect() as db:
            cid, other_cid = [db.execute('SELECT composite_id FROM session_finals WHERE session_id=?',
                                        (session,)).fetchone()[0] for session in (sid, other_sid)]
        path = settings.storage_root / f'composites/{sid}/{cid}.png'
        other = settings.storage_root / f'composites/{other_sid}/{other_cid}.png'
        original = other.read_bytes()
        route = f'/api/admin/sessions/{sid}/composites/{cid}'
        assert client.delete(route).status_code == 403  # Host cookie without CSRF
        assert client.delete(f'/api/admin/sessions/{other_sid}/composites/{cid}', headers=csrf).status_code == 404
        assert client.delete(route, headers=csrf).status_code == 202
        assert path.is_file()
        assert client.get(f'/event-display/media/{display}').status_code == 404
        assert client.get(f'/gallery/photo/{display}/download').status_code == 404
        token = share['share_url'].rsplit('/', 1)[1]
        for suffix in ('', '/image', '/download'):
            assert client.get(f'/p/{token}{suffix}').status_code == 404
        assert [i['id'] for i in client.get('/event-display/api/photos').json()['items']] == [other_display]
        assert [i['id'] for i in client.get('/gallery/api/photos').json()['items']] == [other_display]
        assert approve(client, sid, csrf).status_code == 409
        assert client.post(f'/api/sessions/{sid}/finalize', headers=headers(key()),
                           json={'composite_id':cid}).status_code == 404
        assert repo.cloud.process_deletion()
        assert client.delete(route, headers=csrf).json() == {'state':'deleted'}
        assert not path.exists() and other.read_bytes() == original
        assert client.get(other_share['share_url'].split('photos.test')[1] + '/download').content == original


def test_remote_deletion_retries_after_restart_without_reupload(settings):
    settings = replace(settings, google_drive_enabled=True)
    with TestClient(create_app(settings)) as client:
        repo = client.app.state.repository
        repo.drive.stop()
        repo.cloud.stop()
        fake = repo.drive.client = FakeDrive()
        csrf = login(client, settings)
        sid, _, _ = publish(client, csrf)
        with repo.db.connect() as db:
            cid = db.execute('SELECT composite_id FROM session_finals WHERE session_id=?',(sid,)).fetchone()[0]
            db.execute('UPDATE cloud_publications SET remote_started=1 WHERE composite_id=?',(cid,))
        assert repo.drive.process_one()
        path = settings.storage_root / f'composites/{sid}/{cid}.png'
        def delete_drive(file_id, item):
            assert (file_id, item) == ('reserved-1', cid)
            del fake.files[file_id]
        fake.delete_composite = delete_drive
        def configure_cloud(publisher):
            publisher.origin = 'https://event.invalid'
            publisher.secret = 'fixture-secret' * 4
            publisher.blob_token = 'fixture'
        def cloud_offline(payload, *, method):
            assert (payload, method) == ({'id':cid}, 'DELETE')
            raise TimeoutError('Fixture cloud outage')
        configure_cloud(repo.cloud)
        repo.cloud.register = cloud_offline
        route = f'/api/admin/sessions/{sid}/composites/{cid}'
        assert client.delete(route, headers=csrf).status_code == 202
        assert repo.cloud.process_deletion()
        assert not fake.files and path.is_file()
        assert not repo.drive.process_one() and not repo.cloud.process_one()

        restarted = Repository(settings)
        restarted.drive.client = fake
        configure_cloud(restarted.cloud)
        def delete_cloud(payload, *, method):
            assert (payload, method) == ({'id':cid}, 'DELETE')
            return {'deleted':cid}
        restarted.cloud.register = delete_cloud
        assert client.delete(route, headers=csrf).status_code == 202
        assert restarted.cloud.process_deletion()
        assert not path.exists() and not restarted.cloud.process_one()
        assert client.delete(route, headers=csrf).json() == {'state':'deleted'}


def test_drive_hard_delete_requires_matching_photo_and_ack(settings):
    drive = GoogleDriveClient(settings)
    drive.metadata = lambda _: {'id':'drive-id','mimeType':'image/png','appProperties':{'photobooth_composite':'a'}}
    calls = []
    def request(*args, **kwargs):
        calls.append((args,kwargs))
        return SimpleNamespace(status_code=204)
    drive.request = request
    with pytest.raises(DriveError):
        drive.delete_composite('drive-id','b')
    assert not calls
    drive.delete_composite('drive-id','a')
    assert calls == [(('DELETE','drive/v3/files/drive-id'),{'params':{'supportsAllDrives':'true'}})]
    drive.request = lambda *args, **kwargs: None
    with pytest.raises(DriveError):
        drive.delete_composite('drive-id','a')
