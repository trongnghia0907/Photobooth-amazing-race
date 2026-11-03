from dataclasses import replace
from io import BytesIO
import json,time
import zxingcpp
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app
from app.public_main import create_public_app
from test_printing import settings,enqueue
from test_sharing import finalized
from test_drive_storage import setup,confirmed,finalize
from test_sessions import headers

def decode(data):return zxingcpp.read_barcode(Image.open(BytesIO(data))).text

def test_drive_uses_print_ready_without_changing_official_composite(setup):
    client,repo,fake,settings=setup
    https=replace(settings,public_base_url='https://photos.test');repo.settings=https;repo.sharing.settings=https
    sid,cid=confirmed(client,6);repo.drive.process_one();share=finalize(client,sid,cid).json()['share']
    with TestClient(create_public_app(https)) as public:
        public.app.state.repository.drive.client=fake
        data=public.get(share['image_url']).content
        assert data==public.get(share['download_url']).content
        assert decode(data)==share['share_url']
        with repo.db.connect() as db:source=db.execute('SELECT path FROM composites WHERE id=?',(cid,)).fetchone()[0]
        official=(settings.storage_root/source).read_bytes()
        assert next(iter(fake.files.values()))==official
        original=Image.open(BytesIO(official)).convert('RGB');printed=Image.open(BytesIO(data))
        assert printed.crop((0,0,*original.size)).tobytes()==original.tobytes()
        assert share['print_ready']['qr_y']>=original.height

def test_tunnel_change_preserves_old_files_and_token_and_blocks_local_print(settings):
    local=replace(settings,public_base_url='http://localhost:8000')
    with TestClient(create_app(local)) as client:
        sid,_,state=finalized(client);share=state['share'];token=share['share_url'].split('/p/')[1]
        assert share['print_ready'] is None and not share['qr_embedded']
        assert 'HTTPS' in share['print_ready_error']
        assert enqueue(client,sid,state).status_code==503
        repo=client.app.state.repository;marker=local.storage_root/'.mobile-qr-origin.json'
        for origin in ['https://first.trycloudflare.com','https://second.trycloudflare.com']:
            marker.write_text(json.dumps({'phase':'ready','origin':origin,'expires_at':time.time()+100}))
            updated=client.get('/api/sessions/'+sid,headers=headers()).json()['share']
            assert updated['print_ready'] and updated['qr_embedded']
            data=client.get(updated['image_url']).content
            assert decode(data)==origin+'/p/'+token
            assert updated['share_url']==origin+'/p/'+token
            with repo.db.connect() as db:path=local.storage_root/db.execute('SELECT path FROM print_ready WHERE final_id=?',(share['final_id'],)).fetchone()[0]
            if origin.startswith('https://first'):old=path;old_bytes=path.read_bytes()
        assert old.is_file() and old.read_bytes()==old_bytes and old!=path
        marker.write_text(json.dumps({'phase':'disconnected','expires_at':0}))
        pending=client.get('/api/sessions/'+sid,headers=headers()).json()['share']
        assert not pending['qr_embedded'] and pending['print_ready'] is None
        assert enqueue(client,sid,state).status_code==503
