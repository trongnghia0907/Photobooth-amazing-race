from hashlib import sha256
from io import BytesIO
import time

import pytest
import zxingcpp
from PIL import Image

from app.services.repository import Repository
from app.services.printers import printable_box
from test_drive_storage import confirmed, finalize, setup  # Reuse the independent Drive fixture.
from test_event_display import approve
from test_printing import login
from test_sessions import headers, key


@pytest.mark.parametrize('count', [4, 6])
def test_confirm_and_publish_after_restart_without_duplicate_objects(setup, count):
    client, repo, drive, settings = setup
    repo.cloud.stop()
    sid, final_id = confirmed(client,count)
    path = settings.storage_root / f'composites/{sid}/{final_id}.png'
    original = path.read_bytes()
    assert client.get(f'/api/sessions/{sid}/cloud-share',headers=headers()).json() == {'state':'local'}
    assert not repo.cloud.process_one()
    csrf = login(client,settings)
    assert approve(client,sid,csrf).status_code == 200
    assert not drive.files
    assert repo.drive.process_one()
    assert list(drive.files.values()) == [original]

    objects = {}
    registered = {}
    expires = time.time() + 86400
    fail_thumbnail_once = True

    def upload(key, data, mime):
        nonlocal fail_thumbnail_once
        assert sha256(data).hexdigest() in key and key.startswith(f'photos/{final_id}/')
        if mime=='image/jpeg' and fail_thumbnail_once:
            fail_thumbnail_once = False
            raise TimeoutError('Simulated upload interrupted after PNG was stored')
        assert objects.setdefault(key,(data,mime)) == (data,mime)

    def register(item):
        registered[item['id']] = item
        return {'version':item['version'],'expires_at':expires,
                'share_path':f'/p/{final_id}.'+'a'*64}

    for publisher in (repo.cloud,Repository(settings).cloud):
        publisher.origin = 'https://event.invalid'
        publisher.secret = 'disposable-secret'*3
        publisher.blob_token = 'fixture-only'
        publisher.upload = upload
        publisher.register = register
        assert publisher.share(sid,headers()['Authorization'].split()[1])['state'] == 'pending'
        assert publisher.process_one()
        with repo.db.connect() as db:
            db.execute('UPDATE cloud_publications SET next_attempt=0')
    assert len(objects) == 2 and len(registered) == 1
    assert next(data for data,mime in objects.values() if mime=='image/png') == original
    thumbnail = next(data for data,mime in objects.values() if mime=='image/jpeg')
    with Image.open(BytesIO(thumbnail)) as image:
        assert image.size == ((600,400) if count==4 else (400,600))
    status = client.get(f'/api/sessions/{sid}/cloud-share',headers=headers()).json()
    assert status['state'] == 'ready' and status['qr_image_data'].startswith('data:image/png;base64,')
    assert client.get(f'/api/sessions/{sid}/cloud-share',headers={'Authorization':'Bearer '+'a'*32}).status_code in (401,403,404)

    assert approve(client,sid,csrf,approved=False).status_code == 200
    assert client.get(f'/api/sessions/{sid}/cloud-share',headers=headers()).json() == {'state':'local'}
    assert publisher.process_one()
    assert registered[final_id] == {'id':final_id,'version':2,'approved':False}
    assert path.read_bytes() == original
    with pytest.raises(Exception,match='cloud'):
        repo.drive.evict(final_id)


def test_confirmed_cloud_qr_preview_and_print_use_the_same_asset(setup, caplog):
    client, repo, _, settings = setup
    repo.cloud.stop()
    client.app.state.printing.stop()
    cloud = repo.cloud
    cloud.origin, cloud.secret, cloud.blob_token = 'https://event.invalid', 'fixture'*8, 'fixture'
    uploads = []
    cloud.upload = lambda path, data, mime: uploads.append(mime)
    sid, cid = confirmed(client)
    assert cloud.work_available.is_set()
    cloud.register = lambda item: {
        'version':item['version'], 'expires_at':time.time()+600, 'share_path':f'/p/{cid}.'+'a'*64,
    }
    share = finalize(client,sid,cid).json()['share']
    assert not share['print_ready']
    csrf = login(client,settings)
    assert approve(client,sid,csrf).status_code == 200
    url = f'/api/sessions/{sid}/cloud-share'
    assert client.get(url,headers=headers()).json()['state'] == 'pending'
    with caplog.at_level('INFO'):
        assert cloud.process_one()
    print(next(line for line in caplog.messages if 'share_since_confirm_ms=' in line))
    status = client.get(url,headers=headers()).json()
    assert status['share_url'] == f'{cloud.origin}/p/{cid}.'+'a'*64
    repo.print_ready.backfill(share['final_id'])
    asset = client.get(url,headers=headers()).json()['print_asset']
    query = {'print_ready':1,'v':asset['print_ready_version']}
    preview = client.get(asset['image_url'],params=query).content
    assert preview == client.get(asset['download_url'],params=query).content
    original = client.get(asset['download_url']).content
    with Image.open(BytesIO(preview)) as printed, Image.open(BytesIO(original)) as clean:
        assert printed.width == clean.width
        assert printed.crop((0,0,*clean.size)).tobytes() == clean.convert('RGB').tobytes()
        assert zxingcpp.read_barcode(printed).text == status['share_url']
        assert set(printed.crop((0,clean.height,printed.width,printed.height)).getcolors()) == set(
            printed.crop((0,clean.height,printed.width,printed.height)).getcolors(2))
    response = client.post(f'/api/sessions/{sid}/print-jobs',headers=headers(key()),
        json={'final_id':asset['final_id'],'print_ready_version':asset['print_ready_version']})
    assert response.status_code == 200, response.text
    with repo.db.connect() as db:
        job = db.execute('SELECT * FROM print_jobs WHERE id=?',(response.json()['id'],)).fetchone()
        assert job['sha256'] == sha256(preview).hexdigest()
        assert (settings.storage_root/job['print_ready_file']).read_bytes() == preview
    assert uploads == ['image/png','image/jpeg']
    assert approve(client,sid,csrf,approved=False).status_code == 200
    assert client.get(asset['image_url'],params=query).status_code == 409
    assert client.app.state.printing.process_one()
    with repo.db.connect() as db:
        assert db.execute('SELECT status FROM print_jobs WHERE id=?',(job['id'],)).fetchone()['status'] == 'failed'


def test_local_reapproval_does_not_enroll_historical_final(setup):
    client, repo, _, settings = setup
    sid, final_id = confirmed(client)
    with repo.db.connect() as db:
        db.execute('DELETE FROM cloud_publications WHERE composite_id=?',(final_id,))
    assert approve(client,sid,login(client,settings)).status_code == 200
    assert not repo.cloud.process_one()
    assert len(client.get('/event-display/api/photos').json()['items']) == 1


@pytest.mark.parametrize('image_size',[(1800,1200),(1200,1800)])
def test_print_box_contains_and_preserves_physical_ratio_on_asymmetric_dpi(image_size):
    left, top, right, bottom = printable_box(1200,1800,300,600,*image_size)
    assert 0 <= left < right <= 1200 and 0 <= top < bottom <= 1800
    assert abs(left - (1200-right)) <= 1 and abs(top - (1800-bottom)) <= 1
    assert ((right-left)/300)/((bottom-top)/600) == pytest.approx(image_size[0]/image_size[1],rel=.002)


def test_printer_media_configuration_and_preview_are_snapshotted_in_local_queue(setup):
    client, _, _, settings = setup
    service = client.app.state.printing
    service.stop()
    sid, cid = confirmed(client)
    final = finalize(client,sid,cid).json()['share']['final_id']
    csrf = login(client,settings)
    service.adapter.capabilities = lambda _: {'papers':[{'id':9,'name':'Fixture media','width_mm':210,'height_mm':297}],
                                               'orientations':['portrait','landscape']}
    page = {'ratio':297/210,'left':.05,'top':.05,'width':.9,'height':.9}
    service.adapter.preview = lambda printer,paper,orientation: page
    selected = '/api/admin/printers/selected'
    assert client.put(selected,headers=csrf,json={'printer_id':'mock','paper_id':1}).status_code==422
    assert client.put(selected,headers=csrf,json={'printer_id':'mock','paper_id':9,'orientation':'landscape'}).status_code==200
    assert client.get('/api/admin/printers/preview?printer_id=mock&paper_id=9&orientation=landscape').json()==page
    job = client.post(f'/api/sessions/{sid}/print-jobs',headers=headers(key()),json={'final_id':final,'copies':2}).json()
    assert (job['status'],job['paper_id'],job['orientation'],job['copies']) == ('queued',9,'landscape',2)
