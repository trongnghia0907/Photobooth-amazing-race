from datetime import datetime,timezone,timedelta
from pathlib import Path
import httpx,pytest
from fastapi.testclient import TestClient
from app.public_main import create_public_app
from app.services.repository import Repository
from app.services import sharing
from test_drive_storage import setup,confirmed,finalize
from test_sessions import headers
from test_printing import login

def test_first_verified_public_issuance_expires_once_in_utc_and_preserves_photos(setup,monkeypatch):
    client,repo,fake,settings=setup;sid,cid=confirmed(client,6)
    state=finalize(client,sid,cid).json();share=state['share'];token=share['share_url'].rsplit('/',1)[1]
    assert share['expires_at'] is None
    class Clock(datetime):
        current=datetime.now(timezone.utc)
        @classmethod
        def now(cls,tz=None):return cls.current
    monkeypatch.setattr(sharing,'datetime',Clock)
    with repo.db.connect() as db:fingerprint=db.execute('SELECT sha256 FROM composites WHERE id=?',(cid,)).fetchone()[0]
    class Probe:
        healthy=False
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url):
            if not self.healthy:raise httpx.ConnectError('offline')
            return httpx.Response(200,json={'registered':True,'fingerprint':fingerprint})
    monkeypatch.setattr(httpx,'Client',Probe)
    monkeypatch.setattr(sharing,'verify_isolation',lambda origin: {'routes':22})
    with pytest.raises(Exception):repo.sharing.verify_public(sid,'a'*64)
    assert repo.get(sid,'a'*64)['share']['expires_at'] is None
    Probe.healthy=True;issued=repo.sharing.verify_public(sid,'a'*64)
    deadline=datetime.fromisoformat(issued['expires_at'])
    assert deadline==Clock.current+timedelta(hours=24) and deadline.utcoffset()==timedelta(0)
    Clock.current+=timedelta(hours=1)
    assert repo.sharing.verify_public(sid,'a'*64)['expires_at']==issued['expires_at']
    restarted=Repository(settings)
    assert restarted.sharing.verify_public(sid,'a'*64)['expires_at']==issued['expires_at']
    assert restarted.get(sid,'a'*64)['share']['share_url']==share['share_url']
    repo.drive.process_one();assert repo.drive.ready(cid) and len(fake.files)==1
    originals=dict(fake.files)
    with TestClient(create_public_app(settings)) as public:
        public.app.state.repository.drive.client=fake
        assert public.get('/p/'+token).status_code==200
        Clock.current=deadline
        for suffix in ['', '/status','/image','/download','/qr.png']:
            assert public.get('/p/'+token+suffix).status_code==404
    assert fake.files==originals
    assert repo.get(sid,'a'*64).get('share') is None
    with pytest.raises(Exception):repo.sharing.verify_public(sid,'a'*64)
    assert client.get(f'/api/sessions/{sid}/composites/{cid}/image',headers=headers()).status_code==200
    login(client,settings)
    assert client.get(f'/api/admin/sessions/{sid}/images/composites/{cid}').status_code==200
    with repo.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM session_finals').fetchone()[0]==1
        assert db.execute('SELECT state FROM drive_uploads WHERE composite_id=?',(cid,)).fetchone()[0]=='SYNCED'
        path=db.execute('SELECT path FROM composites WHERE id=?',(cid,)).fetchone()[0]
    assert (settings.storage_root/path).is_file()
