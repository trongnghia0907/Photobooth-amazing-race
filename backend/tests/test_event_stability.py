"""Thirty sequential simulated sessions. No OS printer/camera or public service."""
import gc
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import threading
import time
import tracemalloc
from fastapi.testclient import TestClient
from PIL import Image
import zxingcpp
from app.config import Settings
from app.main import create_app
from app.services import repository as repository_module
from test_sessions import create,composite,headers,key
from test_camera import connect,capture
from test_printing import login,enqueue
from test_event_display import enable,approve


def test_thirty_sequential_sessions_preserve_finals_queue_gallery_and_recovery(tmp_path,monkeypatch):
    settings=Settings(tmp_path/'runtime',app_env='development',operation_mode='rehearsal',allow_mock_hardware=True,
                      public_base_url='https://photos.test',camera_guest_enabled=True,camera_allow_faults=True,
                      admin_username='stability-test',admin_password=secrets.token_urlsafe(24))
    started=time.perf_counter();samples=[];sessions=[];shares=set();approved=[];shutter_expected=0
    tracemalloc.start()
    try:
        with TestClient(create_app(settings)) as client:
            client.app.state.printing.stop()  # Drive the same durable single worker deterministically.
            csrf=login(client,settings);enable(client,csrf)
            for index in range(30):
                before=time.perf_counter();count=4 if index%2==0 else 6
                sid=create(client,layout='landscape_4' if count==4 else 'grid2x3',slot_count=count)
                base=connect(client,sid);adapter=client.app.state.camera.adapter
                for slot in range(count):
                    operation=key()
                    if index==5 and slot==0:
                        adapter.failure='transfer';failed=capture(client,base,slot,operation)
                        assert failed.status_code==503
                        calls=adapter.shutter_calls
                        result=capture(client,base,slot,operation)
                        assert adapter.shutter_calls==calls
                    else:result=capture(client,base,slot,operation)
                    assert result.status_code==200,result.text
                    state=result.json()['session'];shutter_expected+=1
                    assert capture(client,base,slot,operation).json()==result.json()
                if index%3==0:
                    old=state['photos'][0]['id'];result=capture(client,base,0)
                    assert result.status_code==200;state=result.json()['session'];shutter_expected+=1
                    assert state['photos'][0]['id']!=old
                width,height=(1200,800) if count==4 else (800,1200)
                merged=Image.new('RGB',(width,height),'#1e40af');cell_w=width//2;cell_h=(height-40)//(count//2)
                for photo in state['photos']:
                    payload=client.get(f"/api/sessions/{sid}/photos/{photo['id']}/image",headers=headers()).content
                    with Image.open(BytesIO(payload)) as shot:
                        merged.paste(shot.convert('RGB').resize((cell_w,cell_h)),((photo['slot_index']%2)*cell_w,40+(photo['slot_index']//2)*cell_h))
                image=BytesIO();merged.save(image,'PNG');merged.close();payload=image.getvalue()
                operation=key()
                if index==7:
                    real_write=repository_module.atomic_write
                    def fail_write(*args):raise OSError('Injected final save failure')
                    monkeypatch.setattr(repository_module,'atomic_write',fail_write)
                    assert composite(client,sid,state['shots_revision'],operation,payload).status_code==503
                    assert len(client.get(f'/api/sessions/{sid}',headers=headers()).json()['photos'])==count
                    monkeypatch.setattr(repository_module,'atomic_write',real_write)
                saved=composite(client,sid,state['shots_revision'],operation,payload)
                assert saved.status_code==200,saved.text
                cid=saved.json()['composite']['id'];body={'composite_id':cid}
                assert client.post(f'/api/sessions/{sid}/complete',headers=headers(key()),json=body).status_code==200
                assert client.post(base+'/disconnect',headers=headers()).status_code==200
                final=client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json=body)
                assert final.status_code==200,final.text
                state=final.json();share=state['share']
                assert share['share_url'] not in shares;shares.add(share['share_url'])
                assert client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json=body).json()['share']['share_url']==share['share_url']
                qr=client.get(share['qr_image_url']).content
                with Image.open(BytesIO(qr)) as image:assert zxingcpp.read_barcode(image).text==share['share_url']
                downloaded=client.get(share['download_url']);assert downloaded.status_code==200
                assert client.get(share['share_url']).status_code==200
                request_key=key();job=enqueue(client,sid,state,2,request_key)
                assert job.status_code==200,job.text
                assert enqueue(client,sid,state,2,request_key).json()['id']==job.json()['id']
                assert client.app.state.printing.process_one()
                status=client.app.state.printing.get(job.json()['id'])
                assert status['status']=='submitted' and not status['physical_print_confirmed']
                if index%2==0:
                    assert approve(client,sid,csrf).status_code==200;approved.insert(0,sid)
                gallery=client.get('/event-display/api/photos').json()['items']
                assert len(gallery)==len(approved) and len({item['id'] for item in gallery})==len(approved)
                assert not list((settings.storage_root/'originals'/sid).glob('*.png'))
                assert not list((settings.storage_root/'camera_originals'/sid).glob('*.jpg'))
                assert len(list((settings.storage_root/'composites'/sid).glob('*.png')))==1
                sessions.append((sid,share,hashlib.sha256(downloaded.content).hexdigest()))
                gc.collect();current,peak=tracemalloc.get_traced_memory()
                samples.append({'session':index+1,'shots':count,'seconds':round(time.perf_counter()-before,3),
                                'python_current_mb':round(current/1048576,3),'python_peak_mb':round(peak/1048576,3),'threads':threading.active_count()})
            assert adapter.shutter_calls==shutter_expected
            with client.app.state.repository.db.connect() as db:
                for table,expected in [('session_finals',30),('shares',30),('print_jobs',30),('event_display_photos',15)]:
                    assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==expected
                assert not db.execute("SELECT 1 FROM print_jobs WHERE status!='submitted'").fetchone()
        with TestClient(create_app(settings)) as restarted:
            csrf=login(restarted,settings);enable(restarted,csrf)
            assert len(restarted.get('/event-display/api/photos').json()['items'])==15
            for sid,share,digest in sessions:
                assert hashlib.sha256(restarted.get(share['download_url']).content).hexdigest()==digest
                assert restarted.get(f'/api/sessions/{sid}',headers=headers()).json()['share']['share_url']==share['share_url']
            assert restarted.app.state.camera.adapter.shutter_calls==0
        growth=round(samples[-1]['python_current_mb']-samples[4]['python_current_mb'],3)
        assert growth<16,'Unexpected retained Python allocations after warm-up'
        assert max(sample['threads'] for sample in samples[4:])<=samples[4]['threads']+1
        metrics={'passed':True,'sessions':30,'official_composites':30,'unique_share_tokens':len(shares),'print_jobs':30,
                 'approved_gallery_items':15,'mock_shutter_calls':shutter_expected,'elapsed_seconds':round(time.perf_counter()-started,3),
                 'retained_python_growth_after_warmup_mb':growth,'memory_scope':'tracemalloc Python allocations; not browser heap/native SDK/RSS',
                 'faults_tested':['camera transfer retry without second shutter','composite save failure recovery'],
                 'samples':samples}
        output=os.environ.get('EVENT_STABILITY_REPORT')
        if output:
            path=Path(output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(metrics,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in metrics.items() if k!='samples'}))
    finally:tracemalloc.stop()
