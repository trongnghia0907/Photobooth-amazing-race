"""Phase 4 acceptance; all adapter calls are mock/fakes, never physical output."""
from dataclasses import replace
from io import BytesIO
from urllib.parse import urlsplit
import hashlib
import secrets
import time
import uuid
import pytest
import zxingcpp
from PIL import Image
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.services.printing import PrintingService
from app.services.printers import PrinterError, WindowsPrinterAdapter
from app.services.mock_printer import MockPrinterAdapter
from test_sharing import finalized
from test_sessions import headers, key, create, upload, composite, image


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path/'printing',public_base_url='https://photos.test',app_env='development',
                    admin_username='test-host',admin_password=secrets.token_urlsafe(24))


def login(client,settings):
    result=client.post('/api/admin/login',headers={'X-OSA-Login':'1'},json={'username':settings.admin_username,'password':settings.admin_password})
    assert result.status_code==200,result.text
    return {'X-CSRF-Token':result.json()['csrf_token']}


def enqueue(client,sid,state,copies=1,operation=None):
    return client.post(f'/api/sessions/{sid}/print-jobs',headers=headers(operation or key()),
                       json={'final_id':state['share']['final_id'],'copies':copies})


def wait_job(client,sid,jid):
    for _ in range(100):
        job=client.get(f'/api/sessions/{sid}/print-jobs/{jid}',headers=headers()).json()
        if job['status'] in ('submitted','failed'):return job
        time.sleep(.05)
    raise AssertionError('Worker did not finish')


@pytest.mark.parametrize('layout,count,size',[('landscape_4',4,(1200,800)),('grid2x3',6,(800,1200)),('grid3x2',6,(1200,800))])
def test_print_ready_original_intact_qr_decodes_no_overlap(settings,layout,count,size):
    app=create_app(settings)
    with TestClient(app) as client:
        sid=create(client,layout=layout,slot_count=count)
        for slot in range(count):state=upload(client,sid,slot).json()
        state=composite(client,sid,state['shots_revision'],payload=image('red',size)).json()
        cid=state['composite']['id']
        client.post(f'/api/sessions/{sid}/complete',headers=headers(key()),json={'composite_id':cid})
        state=client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json={'composite_id':cid}).json()
        share=state['share'];assert share['qr_embedded']
        original=client.get(f'/api/sessions/{sid}/composites/{cid}/image',headers=headers()).content
        assert hashlib.sha256(original).hexdigest()==state['composite']['sha256']
        printed=client.get(share['image_url']).content
        assert printed==client.get(share['download_url']).content
        assert hashlib.sha256(printed).hexdigest()==share['print_ready']['sha256']
        meta=share['print_ready'];img=Image.open(BytesIO(printed))
        assert img.crop((0,0,*size)).tobytes()==Image.open(BytesIO(original)).convert('RGB').tobytes()
        assert meta['source_height']==size[1] and meta['qr_y']>=size[1]
        assert zxingcpp.read_barcode(img).text==share['share_url']
        assert meta['width']==size[0] and meta['height']>size[1]


@pytest.mark.parametrize('copies',[1,3])
def test_mock_copies_duplicate_keys_exact_guest_file_restart(settings,copies):
    app=create_app(settings)
    with TestClient(app) as client:
        sid,_,state=finalized(client);operation=key()
        response=enqueue(client,sid,state,copies,operation);assert response.status_code==200,response.text
        job=wait_job(client,sid,response.json()['id'])
        assert job['status']=='submitted' and job['receipt']['copies']==copies
        assert not job['physical_print_confirmed'] and not job['receipt']['printed']
        assert enqueue(client,sid,state,copies,operation).json()['id']==job['id']
        assert enqueue(client,sid,state,2 if copies==1 else 1,operation).status_code==409
        mock=settings.storage_root/'mock_prints'/f"{job['id'].replace('-','')}.png"
        assert mock.read_bytes()==client.get(state['share']['download_url']).content
        assert len(list(mock.parent.glob('*.png')))==1
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(f"/api/sessions/{sid}/print-jobs/{job['id']}",headers=headers()).json()==job
        assert enqueue(restarted,sid,state,copies,operation).json()['id']==job['id']


def test_auth_gallery_idor_csrf_logout_and_credentials_rotation(settings):
    app=create_app(settings)
    with TestClient(app) as client:
        sid,_,state=finalized(client);other,_,second=finalized(client,'blue')
        final=state['share']['final_id'];cid=state['composite']['id']
        protected=['/api/admin/me','/api/admin/status','/api/admin/sessions',f'/api/admin/sessions/{sid}',
                   '/api/admin/print-jobs','/api/admin/printers',f'/api/admin/sessions/{sid}/images/composites/{cid}']
        for path in protected:assert client.get(path).status_code==401
        assert client.post('/api/admin/print-jobs',headers={'Idempotency-Key':key()},json={'session_id':sid,'final_id':final,'copies':1}).status_code==401
        assert client.get('/admin').status_code==200 and sid not in client.get('/admin').text
        assert client.post('/api/admin/login',json={'username':settings.admin_username,'password':settings.admin_password}).status_code==403
        csrf=login(client,settings)
        assert client.get('/api/admin/sessions').json()['total']==2
        assert len(client.get(f'/api/admin/sessions/{sid}').json()['composites'])==1
        assert client.get(f'/api/admin/sessions/{other}/images/composites/{cid}').status_code==404
        assert client.get(f'/api/admin/sessions/{other}/images/print_ready/{final}').status_code==404
        assert client.get('/admin/assets/../photobooth.sqlite3').status_code in (404,422)
        body={'session_id':sid,'final_id':final,'copies':2}
        assert client.post('/api/admin/print-jobs',headers={'Idempotency-Key':key()},json=body).status_code==403
        operation=key();h={**csrf,'Idempotency-Key':operation}
        reprint=client.post('/api/admin/print-jobs',headers=h,json=body);assert reprint.status_code==200,reprint.text
        assert client.post('/api/admin/print-jobs',headers=h,json=body).json()['id']==reprint.json()['id']
        assert client.put('/api/admin/printers/selected',headers=csrf,json={'printer_id':'../../bad'}).status_code==422
        assert client.put('/api/admin/printers/selected',headers=csrf,json={'printer_id':'mock'}).status_code==200
        token=client.cookies.get('osa_host');assert 'HttpOnly' in client.post('/api/admin/login',headers={'X-OSA-Login':'1'},json={'username':settings.admin_username,'password':settings.admin_password}).headers['set-cookie']
        csrf=login(client,settings)
        assert client.post('/api/admin/logout',headers=csrf).status_code==200
        for path in protected:assert client.get(path).status_code==401
        client.cookies.set('osa_host',token,path='/api/admin')
        with TestClient(create_app(replace(settings,admin_password=secrets.token_urlsafe(24)))) as rotated:
            rotated.cookies.set('osa_host',token,path='/api/admin')
            assert rotated.get('/api/admin/sessions').status_code==401
        raw=(settings.storage_root/'photobooth.sqlite3').read_bytes()
        assert settings.admin_password.encode() not in raw and token.encode() not in raw


def test_fifo_failure_controlled_retry_cancel_and_restart_ambiguity(settings):
    app=create_app(settings)
    with TestClient(app) as client:
        service=app.state.printing;service.stop()  # deterministic manual worker with no device
        sid,_,state=finalized(client)
        first=enqueue(client,sid,state).json();second=enqueue(client,sid,state,2).json()
        order=[]
        class Failing(MockPrinterAdapter):
            def print_image(self,path,copies,options):
                order.append(options['job_id'])
                raise PrinterError('Simulated ambiguous spooler failure',uncertain=True)
        service.adapter=Failing(settings.storage_root/'mock_prints')
        assert service.process_one()
        assert service.get(first['id'])['status']=='failed' and service.get(first['id'])['uncertain']
        assert order==[first['id']]
        csrf=login(client,settings)
        retry_headers={**csrf,'Idempotency-Key':key()}
        path=f"/api/admin/print-jobs/{first['id']}/retry"
        assert client.post(path,headers=retry_headers,json={}).status_code==409
        retry=client.post(path,headers=retry_headers,json={'acknowledge_uncertain':True})
        assert retry.status_code==200,retry.text
        assert client.post(path,headers=retry_headers,json={'acknowledge_uncertain':True}).json()['id']==retry.json()['id']
        assert client.post(f"/api/admin/print-jobs/{retry.json()['id']}/cancel",headers=csrf).json()['status']=='cancelled'
        assert service.process_one();assert order==[first['id'],second['id']]
        assert not service.process_one()  # failures never automatically retried
        third=enqueue(client,sid,state).json()
        with service.repo.db.connect() as db:db.execute("UPDATE print_jobs SET status='processing' WHERE id=?",(third['id'],))
    with TestClient(create_app(settings)) as client:
        job=wait_job(client,sid,third['id']);assert job['status']=='failed' and job['uncertain']
        assert not list((settings.storage_root/'mock_prints').glob('*.png'))


def test_validation_no_print_before_save_wrong_owner_or_corrupt_file(settings):
    app=create_app(settings)
    with TestClient(app) as client:
        sid=create(client)
        assert enqueue(client,sid,{'share':{'final_id':str(uuid.uuid4())}}).status_code==409
        sid,_,state=finalized(client)
        for n in [0,-1,4,True,'2',1.5]:assert enqueue(client,sid,state,n).status_code==422
        target=f'/api/sessions/{sid}/print-jobs'
        assert client.post(target,headers=headers(key(),token='b'*64),json={'final_id':state['share']['final_id'],'copies':1}).status_code==404
        with app.state.repository.db.connect() as db:
            path=db.execute('SELECT path FROM print_ready WHERE final_id=?',(state['share']['final_id'],)).fetchone()[0]
        (settings.storage_root/path).write_bytes(b'corrupt')
        assert enqueue(client,sid,state).status_code==409
        assert client.get(f"/api/sessions/{sid}/composites/{state['composite']['id']}/image",headers=headers()).status_code==200


def test_two_workers_share_one_os_lease(settings):
    app=create_app(settings)
    with TestClient(app) as client:
        service=app.state.printing;service.stop();sid,_,state=finalized(client)
        calls=[]
        class Recording(MockPrinterAdapter):
            def print_image(self,path,copies,options):
                calls.append(options['job_id']);time.sleep(.05)
                return super().print_image(path,copies,options)
        a=PrintingService(service.repo,Recording(settings.storage_root/'mock_prints'))
        b=PrintingService(service.repo,Recording(settings.storage_root/'mock_prints'))
        a.start();b.start()
        try:
            jobs=[enqueue(client,sid,state).json() for _ in range(3)]
            for job in jobs:assert wait_job(client,sid,job['id'])['status']=='submitted'
            assert calls==[job['id'] for job in jobs]
        finally:a.stop();b.stop()


def test_disabled_login_and_windows_never_prints_without_opt_in(tmp_path):
    with TestClient(create_app(Settings(tmp_path/'disabled'))) as client:
        assert client.post('/api/admin/login',headers={'X-OSA-Login':'1'},json={'username':'host','password':'unused'}).status_code==503
    with pytest.raises(PrinterError,match='chưa được bật'):
        WindowsPrinterAdapter(False).print_image(tmp_path/'unused.png',1,{'printer_id':'unused','job_id':str(uuid.uuid4())})


def test_windows_gdi_contract_contain_copies_and_ambiguous_failure_without_device(tmp_path,monkeypatch):
    import sys
    from types import SimpleNamespace
    from app.services import printers
    events=[]
    class DC:
        def CreatePrinterDC(self,name):events.append(('printer',name))
        def StartDoc(self,name):events.append(('start',name));return 91
        def GetDeviceCaps(self,n):return 1000 if n==8 else 1500
        def StartPage(self):events.append('page')
        def GetHandleOutput(self):return 123
        def EndPage(self):events.append('endpage')
        def EndDoc(self):events.append('end')
        def AbortDoc(self):events.append('abort')
        def DeleteDC(self):events.append('delete')
    class Dib:
        def __init__(self,img):pass
        def draw(self,handle,box):events.append(('draw',handle,box))
    monkeypatch.setitem(sys.modules,'win32ui',SimpleNamespace(CreateDC=DC))
    from PIL import ImageWin
    monkeypatch.setattr(ImageWin,'Dib',Dib)
    adapter=WindowsPrinterAdapter(True)
    monkeypatch.setattr(adapter,'list_printers',lambda:[{'id':'fake-driver'}])
    source=tmp_path/'input.png';source.write_bytes(image(size=(800,1200)))
    receipt=adapter.print_image(source,2,{'printer_id':'fake-driver','job_id':'test'})
    assert events.count('page')==events.count('endpage')==2
    assert ('draw',123,(0,0,1000,1500)) in events
    assert receipt['spooler_job_id']==91 and not receipt['physical_print_confirmed']
    assert events[-2:]==['end','delete']
    def fail(self):raise OSError('fake driver disconnected')
    monkeypatch.setattr(DC,'EndPage',fail)
    with pytest.raises(PrinterError) as caught:adapter.print_image(source,1,{'printer_id':'fake-driver','job_id':'test'})
    assert caught.value.uncertain and events[-2:]==['abort','delete']


def test_legacy_phase3_share_backfill_preserves_token_and_original(settings):
    app=create_app(settings)
    with TestClient(app) as client:
        sid,operation,state=finalized(client)
        share=state['share'];repo=app.state.repository
        with repo.db.connect() as db:
            path=db.execute('SELECT path FROM print_ready WHERE final_id=?',(share['final_id'],)).fetchone()[0]
            db.execute('DELETE FROM print_ready WHERE final_id=?',(share['final_id'],))
        (settings.storage_root/path).unlink()
        result=client.post(f'/api/sessions/{sid}/finalize',headers=headers(operation),json={'composite_id':state['composite']['id']}).json()
        assert result['share']==share
        assert client.get(share['download_url']).status_code==200


def test_persisted_queued_job_runs_after_restart_and_owner_cannot_read_other_job(settings):
    app=create_app(settings)
    with TestClient(app) as client:
        app.state.printing.stop();sid,_,state=finalized(client)
        pending=enqueue(client,sid,state,2).json();assert pending['status']=='queued'
        other=create(client)
        assert client.get(f"/api/sessions/{other}/print-jobs/{pending['id']}",headers=headers()).status_code==404
        assert client.get(f"/api/sessions/{sid}/print-jobs/{pending['id']}",headers=headers(token='b'*64)).status_code==404
    with TestClient(create_app(settings)) as client:
        result=wait_job(client,sid,pending['id'])
        assert result['status']=='submitted' and result['receipt']['copies']==2


def test_worker_missing_file_fails_without_dispatch_then_continues_fifo(settings):
    app=create_app(settings)
    with TestClient(app) as client:
        service=app.state.printing;service.stop()
        a,_,first=finalized(client);b,_,second=finalized(client)
        bad=enqueue(client,a,first).json();good=enqueue(client,b,second).json()
        with service.repo.db.connect() as db:
            relative=db.execute('SELECT print_ready_file FROM print_jobs WHERE id=?',(bad['id'],)).fetchone()[0]
        (settings.storage_root/relative).unlink()
        assert service.process_one()
        job=service.get(bad['id']);assert job['status']=='failed' and not job['uncertain']
        assert service.process_one() and service.get(good['id'])['status']=='submitted'
        assert not service.process_one()
        assert len(list((settings.storage_root/'mock_prints').glob('*.png')))==1


def test_login_rate_limit_secure_cookie_and_unicode_username(settings):
    with TestClient(create_app(settings)) as client:
        for _ in range(5):
            assert client.post('/api/admin/login',headers={'X-OSA-Login':'1'},json={'username':'bad','password':'bad'}).status_code==401
        assert client.post('/api/admin/login',headers={'X-OSA-Login':'1'},json={'username':settings.admin_username,'password':settings.admin_password}).status_code==429
    production=replace(settings,app_env='production',admin_username='Chủ máy')
    with TestClient(create_app(production),base_url='https://testserver') as client:
        result=client.post('/api/admin/login',headers={'X-OSA-Login':'1'},json={'username':production.admin_username,'password':production.admin_password})
        assert result.status_code==200 and 'Secure' in result.headers['set-cookie']
        assert client.get('/api/admin/sessions').status_code==200


def test_expired_share_is_never_printed(settings):
    app=create_app(settings)
    with TestClient(app) as client:
        sid,_,state=finalized(client)
        with app.state.repository.db.connect() as db:
            db.execute("UPDATE shares SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",(state['share']['final_id'],))
        assert enqueue(client,sid,state).status_code==409
        assert client.get(state['share']['image_url']).status_code==404


def test_windows_driver_discovery_failure_reports_unavailable(settings,monkeypatch):
    import sys
    from types import SimpleNamespace
    from app.services.repository import Repository
    class SpoolerError(Exception):pass
    def unavailable(*args):raise SpoolerError('simulated stopped spooler')
    monkeypatch.setitem(sys.modules,'win32print',SimpleNamespace(EnumPrinters=unavailable,PRINTER_ENUM_LOCAL=2,PRINTER_ENUM_CONNECTIONS=4))
    assert WindowsPrinterAdapter(True).list_printers()==[]
    service=PrintingService(Repository(replace(settings,printer_mode='windows',enable_physical_printing=True)))
    assert service.config()['available'] is False


def test_share_revoked_while_queued_never_dispatches_and_root_opens_login(settings):
    app=create_app(settings)
    with TestClient(app) as client:
        service=app.state.printing;service.stop()
        assert client.get('/',follow_redirects=False).headers['location']=='/admin'
        assert 'Đăng nhập' in client.get('/').text
        sid,_,state=finalized(client);job=enqueue(client,sid,state).json()
        with service.repo.db.connect() as db:db.execute('UPDATE shares SET revoked_at=? WHERE id=?',('2026-10-30',state['share']['final_id']))
        assert service.process_one()
        result=service.get(job['id']);assert result['status']=='failed' and not result['uncertain']
        assert not list((settings.storage_root/'mock_prints').glob('*.png'))
