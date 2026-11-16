"""Approved-only small sidebar derivatives; originals and projection unchanged."""
from io import BytesIO
import hashlib

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.main import create_app
from test_event_display import saved, approve
from test_deployment import settings, pair
from test_printing import login
from test_sessions import create,upload,composite,headers,key


def pair_kiosk(client,settings):
    station=pair(client,settings)
    client.cookies.set('osa_booth',station['Cookie'].split('=',1)[1],path='/api')
    client.headers['X-Booth-CSRF']=station['X-Booth-CSRF']


@pytest.mark.parametrize('count',[4,6])
def test_sidebar_thumbnail_is_bounded_cached_and_revocable(settings,count):
    with TestClient(create_app(settings),base_url='http://localhost:8000',client=('127.0.0.1',123)) as client:
        assert client.get('/api/booth/recent-photos').status_code==401
        pair_kiosk(client,settings)
        sid,state=saved(client,count);csrf=login(client,settings)
        assert client.get('/api/booth/recent-photos').json()['items']==[]
        assert approve(client,sid,csrf).status_code==200
        item=client.get('/api/booth/recent-photos').json()['items'][0]
        assert item['image_url'].endswith('?thumbnail=true')
        response=client.get(item['image_url']);assert response.status_code==200
        assert response.headers['content-type']=='image/jpeg'
        with Image.open(BytesIO(response.content)) as image:
            assert max(image.size)==480
            assert image.width/image.height==pytest.approx(state['composite']['width']/state['composite']['height'],abs=.01)
        cache=list((settings.storage_root/'event_previews').glob('*.jpg'))
        assert len(cache)==1;mtime=cache[0].stat().st_mtime_ns
        assert client.get(item['image_url']).content==response.content
        assert cache[0].stat().st_mtime_ns==mtime
        original=client.get(item['image_url'].split('?')[0]).content
        assert hashlib.sha256(original).hexdigest()==state['composite']['sha256']
        assert approve(client,sid,csrf,approved=False).status_code==200
        assert client.get(item['image_url']).status_code==404  # Even with a warm cache.
        assert client.get('/api/booth/recent-photos').json()['items']==[]


def test_photographic_sidebar_payload_is_smaller_without_changing_original(settings):
    with TestClient(create_app(settings),base_url='http://localhost:8000',client=('127.0.0.1',123)) as client:
        pair_kiosk(client,settings)
        sid=create(client,layout='landscape_4',slot_count=4)
        for slot in range(4):state=upload(client,sid,slot).json()
        output=BytesIO();Image.effect_noise((1200,800),80).convert('RGB').save(output,format='PNG')
        state=composite(client,sid,state['shots_revision'],payload=output.getvalue()).json()
        assert client.post(f'/api/sessions/{sid}/complete',headers=headers(key()),json={'composite_id':state['composite']['id']}).status_code==200
        csrf=login(client,settings);assert approve(client,sid,csrf).status_code==200
        item=client.get('/api/booth/recent-photos').json()['items'][0]
        full=client.get(item['image_url'].split('?')[0]).content
        thumb=client.get(item['image_url']).content
        assert hashlib.sha256(full).hexdigest()==state['composite']['sha256']
        assert len(thumb)<len(full)
        print(f'SYNTHETIC sidebar payload: original PNG={len(full)} bytes; thumbnail JPEG={len(thumb)} bytes')
