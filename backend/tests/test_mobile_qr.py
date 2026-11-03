from dataclasses import replace
from io import BytesIO
import json
import time
from fastapi.testclient import TestClient
from PIL import Image
import zxingcpp
from app.config import Settings
from app.main import create_app
from app.public_main import create_public_app
from test_sharing import finalized
from test_sessions import headers,key


def test_temporary_origin_refresh_preserves_tokens_photos_and_print_ready(tmp_path,monkeypatch):
    settings=Settings(tmp_path/'mobile',app_env='development',operation_mode='rehearsal',allow_mock_hardware=True,
                      public_base_url='http://localhost:8000')
    monkeypatch.setenv('MOBILE_QR_PHOTO_ONLY','true')
    with TestClient(create_app(settings)) as private:
        sid,operation,first=finalized(private)
        other,_,second=finalized(private,'green')
        assert first['share']['share_url']!=second['share']['share_url']
        token=first['share']['share_url'].rsplit('/',1)[1]
        before={path.relative_to(settings.storage_root):path.read_bytes() for folder in ('composites','print_ready','qrcodes')
                for path in (settings.storage_root/folder).rglob('*.png')}
        marker=settings.storage_root/'.mobile-qr-origin.json'
        marker.write_text(json.dumps({'origin':'https://mobile-demo-test.trycloudflare.com','expires_at':time.time()+600,'run_id':'test'}))
        health=private.get('/api/health').json()['sharing']
        assert health['temporary'] and not health['local_only']
        refreshed=private.post(f'/api/sessions/{sid}/finalize',headers=headers(operation),
                               json={'composite_id':first['composite']['id']}).json()
        assert refreshed['share']['share_url']=='https://mobile-demo-test.trycloudflare.com/p/'+token
        assert refreshed['share']['final_id']==first['share']['final_id']
        with TestClient(create_public_app(settings)) as public:
            png=public.get('/p/'+token+'/qr.png')
            assert zxingcpp.read_barcode(Image.open(BytesIO(png.content))).text==refreshed['share']['share_url']
            assert public.get('/p/'+token).status_code==200
            assert public.get('/p/'+token+'/download').content==private.get(first['share']['download_url']).content
            for route in ['/','/admin','/api/admin/login','/api/admin/camera','/api/admin/print-jobs','/api/booth/pair',
                          '/api/sessions','/gallery','/.env','/docs','/openapi.json','/healthz','/p/invalid','/p/'+'x'*43]:
                assert public.get(route).status_code==404,route
            assert public.post('/p/'+token).status_code==405
            assert not hasattr(public.app.state,'camera') and not hasattr(public.app.state,'printing')
        after={path.relative_to(settings.storage_root):path.read_bytes() for folder in ('composites','print_ready','qrcodes')
               for path in (settings.storage_root/folder).rglob('*.png')}
        # Existing originals/artifacts remain intact; changing HTTPS origin
        # appends a new print-ready derivative containing the current QR URL.
        assert all(after[path]==data for path,data in before.items())
        added=set(after)-set(before)
        assert len(added)==1
        for path in added:
            assert path.parts[:2]==('print_ready',sid)
            assert zxingcpp.read_barcode(Image.open(BytesIO(after[path]))).text==refreshed['share']['share_url']
        with private.app.state.repository.db.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM shares').fetchone()[0]==2
            assert db.execute('SELECT COUNT(*) FROM session_finals').fetchone()[0]==2
        marker.unlink()
        assert private.get(f'/api/sessions/{sid}',headers=headers()).json()['share']['share_url']==first['share']['share_url']


def test_tunnel_health_lease_connecting_disconnect_and_restart(tmp_path):
    from app.services.repository import Repository
    root=tmp_path/'lease'
    repo=Repository(Settings(root,app_env='development',public_base_url='http://localhost:8000'))
    marker=root/'.mobile-qr-origin.json'
    for data,expected in [
        ({'phase':'connecting','expires_at':time.time()+60},'connecting'),
        ({'phase':'ready','origin':'https://live-test.trycloudflare.com','expires_at':time.time()+30},'ready'),
        ({'phase':'ready','origin':'https://live-test.trycloudflare.com','expires_at':time.time()-1},'disconnected'),
        ({'phase':'disconnected','expires_at':0},'disconnected'),
        ({'phase':'ready','origin':'https://new-test.trycloudflare.com','expires_at':time.time()+30},'ready'),
    ]:
        marker.write_text(json.dumps(data))
        config=repo.sharing.configuration()
        assert config['tunnel_status']==expected
        assert config['local_only']==(expected!='ready')
    assert config['base_url']=='https://new-test.trycloudflare.com'


def test_attach_feed_reuses_verified_local_finals_without_waiting_for_drive(tmp_path):
    import importlib.util
    import sys
    from pathlib import Path
    scripts=Path(__file__).resolve().parents[2]/'scripts'
    sys.path.insert(0,str(scripts))
    try:
        spec=importlib.util.spec_from_file_location('mobile_attach_test',scripts/'mobile_qr_demo.py')
        mobile=importlib.util.module_from_spec(spec);spec.loader.exec_module(mobile)
        settings=Settings(tmp_path/'attach',app_env='development',public_base_url='http://localhost:8000')
        with TestClient(create_app(settings)) as private:
            sid,_,first=finalized(private)
            repo=private.app.state.repository
            assert len(mobile.existing_photos(settings))==1
            with repo.db.connect() as db:
                db.execute('INSERT INTO drive_uploads(composite_id) VALUES (?)',(first['composite']['id'],))
            pending=mobile.existing_photos(settings)
            assert len(pending)==1 and pending[0]['session_id']==sid
            assert not pending[0]['share'].get('public_ready',False)
            with repo.db.connect() as db:
                assert db.execute('SELECT COUNT(*) FROM shares').fetchone()[0]==1
                db.execute("UPDATE drive_uploads SET state='SYNCED'")
            assert len(mobile.existing_photos(settings))==1
            # Removing only this disposable local fixture forces remote
            # retrieval: a manually marked SYNCED row is not remote proof.
            with repo.db.connect() as db:
                path=db.execute('SELECT path FROM composites WHERE id=?',(first['composite']['id'],)).fetchone()[0]
            (settings.storage_root/path).unlink()
            assert mobile.existing_photos(settings)==[]
    finally:sys.path.remove(str(scripts))


def test_override_is_temporary_strict_and_never_used_in_production(tmp_path):
    from app.services.repository import Repository
    storage=tmp_path/'override';repo=Repository(Settings(storage,app_env='development',public_base_url='http://localhost:8000'))
    marker=storage/'.mobile-qr-origin.json'
    for value in [
        {'origin':'https://mobile-test.trycloudflare.com','expires_at':time.time()-1},
        {'origin':'https://attacker.example.com','expires_at':time.time()+600},
        {'origin':'https://mobile-test.trycloudflare.com/extra','expires_at':time.time()+600},
        {'origin':'http://mobile-test.trycloudflare.com','expires_at':time.time()+600},
    ]:
        marker.write_text(json.dumps(value));assert repo.sharing.temporary_origin() is None
    marker.write_text(json.dumps({'origin':'https://mobile-test.trycloudflare.com','expires_at':time.time()+600}))
    production=Repository(replace(repo.settings,app_env='production',public_base_url='https://photos.event.test'))
    assert production.sharing.temporary_origin() is None
    assert production.sharing.configuration()['base_url']=='https://photos.event.test'
