from dataclasses import replace
import hashlib
import secrets
import sqlite3
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from test_sessions import create,upload,six_photos,composite,headers,key,image
from test_printing import login


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path/'storage',public_base_url='http://localhost:8000',app_env='development',
                    admin_username='test-host',admin_password=secrets.token_urlsafe(24),camera_guest_enabled=True)


def draft(client,count=6):
    sid=create(client,slot_count=count,layout='landscape_4' if count==4 else 'grid2x3')
    for slot in range(count):state=upload(client,sid,slot).json()
    state=composite(client,sid,state['shots_revision']).json()
    return sid,state


def complete(client,sid,state,operation=None):
    return client.post(f'/api/sessions/{sid}/complete',headers=headers(operation or key()),json={'composite_id':state['composite']['id']})


@pytest.mark.parametrize('count',[4,6])
def test_one_official_final_cleanup_stable_token_and_final_only_host(settings,count):
    app=create_app(settings)
    with TestClient(app) as client:
        sid,state=draft(client,count);first_draft=state['composite']['id'];photo=state['photos'][0]['id']
        assert len(list((settings.storage_root/'originals'/sid).glob('*.png')))==count
        state=upload(client,sid,0,payload=image('red')).json()
        state=composite(client,sid,state['shots_revision']).json()
        cid=state['composite']['id']
        login(client,settings)
        assert client.get(f'/api/admin/sessions/{sid}').json()['composites']==[]
        assert client.get(f'/api/admin/sessions/{sid}/images/photos/{photo}').status_code==404
        assert client.get(f'/api/admin/sessions/{sid}/images/composites/{cid}').status_code==404
        operation=key();saved=complete(client,sid,state,operation)
        assert saved.status_code==200,saved.text
        assert saved.json()['finalized'] and saved.json()['cleanup_status']=='complete'
        assert not list((settings.storage_root/'originals'/sid).glob('*.png'))
        assert [p.stem for p in (settings.storage_root/'composites'/sid).glob('*.png')]==[cid]
        assert client.get(f'/api/sessions/{sid}/photos/{photo}/image',headers=headers()).status_code==410
        assert complete(client,sid,state,operation).json()==saved.json()
        assert complete(client,sid,state).json()==saved.json()
        assert upload(client,sid,1).status_code==409
        assert composite(client,sid,state['shots_revision']).status_code==409
        assert client.delete(f'/api/sessions/{sid}/photos',headers=headers(key())).status_code==409
        assert client.post(f'/api/sessions/{sid}/camera/connect',headers=headers()).status_code==409
        assert client.post(f'/api/sessions/{sid}/camera/captures',headers=headers(key()),json={'slot_index':0}).status_code==409
        assert client.get(f'/api/sessions/{sid}/composites/{first_draft}/image',headers=headers()).status_code==410
        body={'composite_id':cid}
        first=client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json=body).json()
        second=client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json=body).json()
        assert first['share']==second['share']
        assert client.get(first['share']['download_url']).status_code==200
        detail=client.get(f'/api/admin/sessions/{sid}').json()
        assert len(detail['composites'])==1 and detail['composites'][0]['id']==cid
        with app.state.repository.db.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM shares WHERE session_id=?',(sid,)).fetchone()[0]==1
            assert db.execute('SELECT COUNT(*) FROM session_finals WHERE session_id=?',(sid,)).fetchone()[0]==1


def test_failed_upload_and_confirmation_preserve_working_assets_and_allow_retake(settings,monkeypatch):
    from app.services import repository as module
    app=create_app(settings)
    with TestClient(app) as client:
        sid=create(client);state=six_photos(client,sid)
        original_write=module.atomic_write
        def full_disk(path,payload):
            if 'composites' in path.parts:raise OSError('simulated full disk')
            return original_write(path,payload)
        monkeypatch.setattr(module,'atomic_write',full_disk)
        assert composite(client,sid,state['shots_revision']).status_code==503
        assert len(list((settings.storage_root/'originals'/sid).glob('*.png')))==6
        monkeypatch.setattr(module,'atomic_write',original_write)
        state=upload(client,sid,0,payload=image('red')).json()
        state=composite(client,sid,state['shots_revision']).json()
        with app.state.repository.db.connect() as db:
            db.executescript("CREATE TRIGGER fail_confirmation BEFORE INSERT ON session_finals BEGIN SELECT RAISE(ABORT,'test'); END;")
        operation=key();assert complete(client,sid,state,operation).status_code==503
        assert client.get(f'/api/sessions/{sid}',headers=headers()).json()['status']=='editing'
        assert len(list((settings.storage_root/'originals'/sid).glob('*.png')))==7
        with app.state.repository.db.connect() as db:db.execute('DROP TRIGGER fail_confirmation')
        assert complete(client,sid,state,operation).status_code==200
        assert not list((settings.storage_root/'originals'/sid).glob('*.png'))


def test_cleanup_failure_is_retried_without_losing_final_or_share(settings,monkeypatch):
    app=create_app(settings)
    with TestClient(app) as client:
        repo=app.state.repository;sid,state=draft(client)
        target=repo.temporary_assets.target
        class Locked:
            def unlink(self,**kwargs):raise PermissionError('simulated locked JPG')
        monkeypatch.setattr(repo.temporary_assets,'target',lambda *args:Locked())
        result=complete(client,sid,state)
        assert result.status_code==200 and result.json()['cleanup_status']=='blocked'
        assert len(list((settings.storage_root/'originals'/sid).glob('*.png')))==6
        body={'composite_id':state['composite']['id']}
        shared=client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json=body).json()
        assert client.get(shared['share']['download_url']).status_code==200
        monkeypatch.setattr(repo.temporary_assets,'target',target)
        repo.temporary_assets.process_pending()
        assert not list((settings.storage_root/'originals'/sid).glob('*.png'))
        assert client.get(f'/api/sessions/{sid}',headers=headers()).json()['cleanup_status']=='complete'
        assert client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json=body).json()['share']==shared['share']


def test_restart_resumes_cleanup_only_when_final_integrity_is_valid(settings,monkeypatch):
    app=create_app(settings)
    with TestClient(app) as client:
        sid,state=draft(client);repo=app.state.repository
        monkeypatch.setattr(repo.temporary_assets,'process_session',lambda sid:None)
        assert complete(client,sid,state).json()['cleanup_status']=='pending'
        path=settings.storage_root/'composites'/sid/(state['composite']['id']+'.png')
        payload=path.read_bytes();path.unlink()
    with TestClient(create_app(settings)) as client:
        client.app.state.repository.temporary_assets.process_pending()
        assert len(list((settings.storage_root/'originals'/sid).glob('*.png')))==6
        assert client.get(f'/api/sessions/{sid}',headers=headers()).json()['cleanup_status']=='blocked'
        path.write_bytes(payload)
        client.app.state.repository.temporary_assets.process_pending()
        assert not list((settings.storage_root/'originals'/sid).glob('*.png'))
        assert hashlib.sha256(path.read_bytes()).hexdigest()==state['composite']['sha256']


def test_cleanup_rejects_traversal_and_never_deletes_another_session(settings,monkeypatch):
    app=create_app(settings)
    with TestClient(app) as client:
        sid,state=draft(client);other,_=draft(client)
        cleanup=app.state.repository.temporary_assets;process=cleanup.process_session
        monkeypatch.setattr(cleanup,'process_session',lambda sid:None)
        assert complete(client,sid,state).status_code==200
        outside=settings.storage_root.parent/'keep.txt';outside.write_text('keep')
        with app.state.repository.db.connect() as db:
            db.execute('INSERT INTO temporary_file_cleanup(session_id,path) VALUES (?,?)',(sid,'../keep.txt'))
        monkeypatch.setattr(cleanup,'process_session',process);cleanup.process_pending()
        assert outside.read_text()=='keep'
        assert len(list((settings.storage_root/'originals'/other).glob('*.png')))==6
        assert (settings.storage_root/'composites'/sid/(state['composite']['id']+'.png')).is_file()
        assert client.get(f'/api/sessions/{sid}',headers=headers()).json()['cleanup_status']=='blocked'
