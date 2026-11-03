from dataclasses import replace
import hashlib
from io import BytesIO
import secrets
import time
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.config import Settings
from app.main import create_app
from app.public_main import create_public_app
from app.services.repository import Repository
from app.services.drive_storage import DriveStorage
from app.services.drive_client import DriveError,GoogleDriveClient
from test_sessions import create,upload,composite,headers,key,image
from test_printing import login,enqueue,wait_job

FOLDER='1ixmork-KFJ8xdtQCFJIpUTQm-SnJqeez'

class FakeDrive:
    def __init__(self):
        self.files={};self.allowed=True;self.offline=False;self.lose_ack=False;self.reserved=0;self.downloads=0
    def privacy(self):
        if self.offline:raise DriveError('Offline; keep staging')
        if not self.allowed:raise DriveError('Folder has anyone permission; blocked')
        return {'private':True,'folder_id':FOLDER}
    def reserve_id(self):self.reserved+=1;return 'reserved-'+str(self.reserved)
    def permissions(self,file_id):return [{'type':'user','role':'owner'}] if self.allowed else [{'type':'anyone','role':'reader'}]
    def upload(self,file_id,path,composite_id):
        if file_id not in self.files:self.files[file_id]=path.read_bytes()
        if self.lose_ack:self.lose_ack=False;raise TimeoutError('Lost successful ACK')
        data=self.files[file_id]
        return {'id':file_id,'parents':[FOLDER],'md5Checksum':hashlib.md5(data).hexdigest(),'size':str(len(data))}
    def download(self,file_id):self.downloads+=1;return self.files[file_id]

@pytest.fixture
def setup(tmp_path):
    settings=Settings(tmp_path/'drive',app_env='development',public_base_url='https://photos.test',
        google_drive_enabled=True,admin_username='host',admin_password=secrets.token_urlsafe(24))
    with TestClient(create_app(settings)) as client:
        repo=client.app.state.repository;repo.drive.stop()
        fake=FakeDrive();repo.drive.client=fake
        yield client,repo,fake,settings

def confirmed(client,count=4):
    sid=create(client,layout='landscape_4' if count==4 else 'grid2x3',slot_count=count)
    for slot in range(count):state=upload(client,sid,slot).json()
    state=composite(client,sid,state['shots_revision'],payload=image('blue',(1200,800) if count==4 else (800,1200))).json()
    cid=state['composite']['id']
    response=client.post(f'/api/sessions/{sid}/complete',headers=headers(key()),json={'composite_id':cid})
    assert response.status_code==200,response.text
    return sid,cid

def finalize(client,sid,cid):
    return client.post(f'/api/sessions/{sid}/finalize',headers=headers(key()),json={'composite_id':cid})

@pytest.mark.parametrize('count',[4,6])
def test_confirm_queue_private_sync_share_download_print_and_safe_cache(setup,count):
    client,repo,fake,settings=setup
    sid,cid=confirmed(client,count)
    path=settings.storage_root/f'composites/{sid}/{cid}.png';original=path.read_bytes()
    early=finalize(client,sid,cid)
    assert early.status_code==200 and early.json()['share']
    with repo.db.connect() as db:
        assert db.execute('SELECT state FROM drive_uploads').fetchone()[0]=='PENDING'
        assert db.execute('SELECT COUNT(*) FROM shares').fetchone()[0]==1
    repo.drive.process_one()
    state=finalize(client,sid,cid).json()
    assert state['share']['share_url'].startswith('https://photos.test/p/')
    assert not any(value in state['share']['share_url'] for value in fake.files)
    with TestClient(create_public_app(settings)) as public:
        public.app.state.repository.drive.client=fake
        token=state['share']['share_url'].rsplit('/',1)[1]
        downloaded=public.get('/p/'+token+'/download')
        assert downloaded.status_code==200
        assert public.get('/p/'+token+'/image').content==downloaded.content
        assert public.get('/p/invalid').status_code==404
        source=Image.open(BytesIO(original)).convert('RGB')
        assert Image.open(BytesIO(downloaded.content)).crop((0,0,*source.size)).tobytes()==source.tobytes()
    job=enqueue(client,sid,state).json();assert wait_job(client,sid,job['id'])['status']=='submitted'
    repo.drive.evict(cid);assert not path.exists()
    assert client.get(f'/api/sessions/{sid}/composites/{cid}/image',headers=headers()).content==original
    assert path.read_bytes()==original
    with repo.db.connect() as db:db.execute('UPDATE shares SET revoked_at=? WHERE composite_id=?',('2020-01-01T00:00:00+00:00',cid))
    before=fake.downloads
    assert client.get('/p/'+token+'/download').status_code==404
    assert fake.downloads==before

def test_offline_and_lost_upload_ack_survive_restart_without_duplicates(setup):
    client,repo,fake,settings=setup
    sid,cid=confirmed(client)
    fake.offline=True;repo.drive.process_one()
    path=settings.storage_root/f'composites/{sid}/{cid}.png';assert path.is_file()
    assert fake.reserved==0
    with repo.db.connect() as db:db.execute('UPDATE drive_uploads SET next_attempt=0')
    fake.offline=False;fake.lose_ack=True;repo.drive.process_one()
    assert len(fake.files)==1 and fake.reserved==1
    restarted=Repository(settings);restarted.drive.client=fake
    with restarted.db.connect() as db:db.execute("UPDATE drive_uploads SET next_attempt=0,state='UPLOADING'")
    restarted.drive.process_one()
    assert restarted.drive.ready(cid) and len(fake.files)==1 and fake.reserved==1 and path.exists()
    with restarted.db.connect() as db:
        assert db.execute('SELECT attempts FROM drive_uploads').fetchone()[0]==2
        assert db.execute('SELECT drive_file_id FROM drive_uploads').fetchone()[0]=='reserved-1'
    assert finalize(client,sid,cid).status_code==200

def test_privacy_and_auth_fail_closed_keep_staging(setup):
    client,repo,fake,settings=setup
    sid,cid=confirmed(client);fake.allowed=False;repo.drive.process_one()
    assert fake.reserved==0 and not fake.files
    # A private local share is independent of a blocked remote upload.
    assert finalize(client,sid,cid).status_code==200
    assert (settings.storage_root/f'composites/{sid}/{cid}.png').exists()
    assert client.get('/api/admin/storage/drive').status_code==401
    assert client.post('/api/admin/storage/drive/test').status_code==401
    csrf=login(client,settings)
    assert client.post('/api/admin/storage/drive/check',headers=csrf).status_code==409
    assert client.post('/api/admin/storage/drive/test',headers=csrf).status_code==409
    assert not fake.files
    assert client.post('/api/admin/storage/drive/retry').status_code==403
    assert client.post('/api/admin/storage/drive/retry',headers=csrf).status_code==200

def test_checksum_mismatch_never_synced_or_cleaned(setup):
    client,repo,fake,settings=setup
    sid,cid=confirmed(client)
    original=fake.upload
    def corrupt(*args):
        metadata=original(*args);metadata['md5Checksum']='bad';return metadata
    fake.upload=corrupt;repo.drive.process_one()
    assert not repo.drive.ready(cid)
    with pytest.raises(Exception):repo.drive.evict(cid)
    assert (settings.storage_root/f'composites/{sid}/{cid}.png').is_file()

def test_strict_acl_rejects_anyone_group_domain_and_unreadable_parent(tmp_path):
    settings=Settings(tmp_path/'acl')
    client=GoogleDriveClient(settings)
    client.metadata=lambda file_id:{'mimeType':'application/vnd.google-apps.folder','capabilities':{'canAddChildren':True},'parents':[]}
    for kind in ('anyone','group','domain'):
        client.permissions=lambda file_id:[{'type':kind}]
        with pytest.raises(DriveError):client.privacy()
    client.permissions=lambda file_id:[{'type':'user'}]
    client.metadata=lambda file_id:({'mimeType':'application/vnd.google-apps.folder','capabilities':{'canAddChildren':True},'parents':['parent']} if file_id==FOLDER else None)
    with pytest.raises(DriveError):client.privacy()
    with pytest.raises(ValueError):replace(settings,google_drive_folder_id='different-folder')

def test_active_print_and_event_approval_keep_local_cache(setup):
    client,repo,fake,settings=setup
    sid,cid=confirmed(client);repo.drive.process_one();state=finalize(client,sid,cid).json()
    client.app.state.printing.stop()
    job=enqueue(client,sid,state).json()
    assert job['status']=='queued'
    with pytest.raises(DriveError,match='job in'):repo.drive.evict(cid)
    path=settings.storage_root/f'composites/{sid}/{cid}.png';assert path.exists()
    with repo.db.connect() as db:db.execute("UPDATE print_jobs SET status='submitted' WHERE id=?",(job['id'],))
    csrf=login(client,settings)
    approved=client.put(f'/api/admin/event-display/photos/{sid}',headers=csrf,
        json={'approved':True,'approval_basis':'guest_consent','consent_confirmed':True})
    assert approved.status_code==200
    with pytest.raises(DriveError,match='trình chiếu'):repo.drive.evict(cid)
    assert path.exists()

def test_limited_access_metadata_only_inheritance_does_not_require_private_parent(tmp_path):
    settings=Settings(tmp_path/'limited')
    client=GoogleDriveClient(settings);reads=[]
    def metadata(file_id):
        reads.append(file_id)
        assert file_id==FOLDER,'Must not evaluate public parent content grants past a proven Limited Access boundary'
        return {'id':FOLDER,'mimeType':'application/vnd.google-apps.folder','inheritedPermissionsDisabled':True,
                'parents':['public-parent'],'capabilities':{'canAddChildren':True}}
    client.metadata=metadata
    client.permissions=lambda file_id:[{'type':'user','role':'owner'},
        {'id':'anyone','type':'anyone','role':'reader','view':'metadata','inheritedPermissionsDisabled':True,
         'permissionDetails':[{'inherited':True,'role':'reader'}]}]
    audit=client.privacy()
    assert audit['private'] and reads==[FOLDER]
    assert audit['evidence'][0]['permissions'][1]['content_access']=='METADATA_ONLY'

@pytest.mark.parametrize('change',[
    {'view':None},
    {'permissionDetails':[{'inherited':False}]},
    {'permissionDetails':[{'inherited':True},{'inherited':False}]},
    {'permissionDetails':[]},
    {'permissionDetails':[{}]},
    {'role':'writer'},
    {'inheritedPermissionsDisabled':False},
])
def test_limited_access_never_hides_direct_ambiguous_or_content_grants(tmp_path,change):
    client=GoogleDriveClient(Settings(tmp_path/'ambiguous'))
    client.metadata=lambda file_id:{'id':FOLDER,'mimeType':'application/vnd.google-apps.folder',
        'inheritedPermissionsDisabled':True,'capabilities':{'canAddChildren':True}}
    permission={'type':'anyone','role':'reader','view':'metadata','permissionDetails':[{'inherited':True}],**change}
    client.permissions=lambda file_id:[{'type':'user','role':'owner'},permission]
    with pytest.raises(DriveError):client.privacy()
    assert not client.last_privacy_audit['private']

def test_file_cannot_use_folder_metadata_view_exception():
    permission={'type':'anyone','role':'reader','view':'metadata','inheritedPermissionsDisabled':True,
                'permissionDetails':[{'inherited':True}]}
    assert not GoogleDriveClient.restricted_permissions({'mimeType':'image/png','inheritedPermissionsDisabled':True},[permission])

@pytest.mark.parametrize('flag',[None,False])
def test_missing_or_disabled_limited_flag_never_assumes_metadata_exception(flag):
    permission={'type':'anyone','role':'reader','view':'metadata','permissionDetails':[{'inherited':True}]}
    metadata={'mimeType':'application/vnd.google-apps.folder','inheritedPermissionsDisabled':flag}
    assert not GoogleDriveClient.restricted_permissions(metadata,[permission])
