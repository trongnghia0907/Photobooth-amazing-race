"""Private Drive adapter. No permission writes; drive.file scope only."""
import hashlib
import json
import os
import threading
from urllib.parse import quote
import httpx
from fastapi import HTTPException
from .images import atomic_write

SCOPE='https://www.googleapis.com/auth/drive.file'

class DriveError(Exception):
    pass

class CredentialStore:
    def __init__(self,root):self.path=root/'.drive-oauth.bin'
    def save(self,value):
        if os.name=='nt':
            import win32crypt
            atomic_write(self.path,win32crypt.CryptProtectData(value.encode(),'Photobooth Drive',None,None,None,0))
        else:
            import keyring
            # Require an OS keychain, never silently use a plaintext fallback.
            if keyring.get_keyring().priority<1:raise DriveError('Configure an OS keychain for OAuth credentials')
            keyring.set_password('AmazingRacePhotobooth',str(self.path),value)
    def load(self):
        try:
            if os.name=='nt':
                import win32crypt
                return win32crypt.CryptUnprotectData(self.path.read_bytes(),None,None,None,0)[1].decode()
            import keyring
            value=keyring.get_password('AmazingRacePhotobooth',str(self.path))
            if not value:raise DriveError('Google OAuth chưa kết nối. Chạy scripts/connect_google_drive.py.')
            return value
        except (OSError,ImportError) as error:
            raise DriveError('Google OAuth chưa kết nối hoặc không giải mã được. Chạy scripts/connect_google_drive.py.') from error

class GoogleDriveClient:
    def __init__(self,settings):
        self.settings=settings;self.store=CredentialStore(settings.storage_root);self.lock=threading.RLock()
    def request(self,method,path,**kwargs):
        try:
            saved=self.store.load()
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            with self.lock:
                credentials=Credentials.from_authorized_user_info(json.loads(saved),[SCOPE])
                if not credentials.valid:
                    credentials.refresh(Request());self.store.save(credentials.to_json())
                response=httpx.request(method,'https://www.googleapis.com/'+path,
                    headers={'Authorization':'Bearer '+credentials.token,**kwargs.pop('headers',{})},timeout=45,**kwargs)
            if response.status_code==404:return None
            if response.status_code>=400:raise DriveError('Google Drive HTTP '+str(response.status_code)+'. Kiểm tra OAuth/quota/quyền thư mục; ảnh local vẫn được giữ.')
            return response
        except DriveError:raise
        except Exception as error:
            # Never echo OAuth response bodies, access tokens, client secrets or paths.
            raise DriveError('Không truy cập được Google Drive. Kiểm tra mạng/OAuth rồi thử lại; giữ ảnh local.') from error
    def metadata(self,file_id):
        response=self.request('GET','drive/v3/files/'+quote(file_id,safe=''),
            params={'fields':'id,name,mimeType,parents,trashed,size,md5Checksum,inheritedPermissionsDisabled,capabilities(canAddChildren,canListChildren)','supportsAllDrives':'true'})
        return response.json() if response else None
    def permissions(self,file_id):
        items=[];token=None
        while True:
            response=self.request('GET','drive/v3/files/'+quote(file_id,safe='')+'/permissions',
                params={'fields':'nextPageToken,permissions(id,type,role,view,inheritedPermissionsDisabled,permissionDetails(inherited,inheritedFrom,permissionType,role))','supportsAllDrives':'true','pageSize':100,**({'pageToken':token} if token else {})})
            if response is None:raise DriveError('Không đọc được quyền đầy đủ của thư mục. Dừng upload.')
            body=response.json();items.extend(body.get('permissions',[]));token=body.get('nextPageToken')
            if not token:return items
    @staticmethod
    def classify_permission(metadata,permission):
        """Classify content access, not just visibility of a folder's name.

        A Limited Access metadata-view permission is explicitly documented by
        Drive as reader + view=metadata + exclusively inherited details. A
        missing field is never inferred from a UI label or a login redirect.
        """
        if permission.get('type')=='user':
            return {'content_access':'NAMED_USER','reason':'Restricted access to a named user'}
        if permission.get('type') not in ('anyone','domain','group'):
            return {'content_access':'UNKNOWN','reason':'Unknown permission type'}
        details=permission.get('permissionDetails')
        limited=metadata.get('mimeType')=='application/vnd.google-apps.folder' and metadata.get('inheritedPermissionsDisabled') is True
        exclusively_inherited=isinstance(details,list) and bool(details) and all(item.get('inherited') is True for item in details)
        has_direct=isinstance(details,list) and any(item.get('inherited') is False for item in details)
        metadata_only=(limited and permission.get('view')=='metadata' and permission.get('role')=='reader'
                       and permission.get('inheritedPermissionsDisabled') is not False and exclusively_inherited)
        if metadata_only:
            return {'content_access':'METADATA_ONLY','reason':'Limited Access blocks inherited content access'}
        if has_direct:
            return {'content_access':'BROAD_CONTENT','reason':'Direct broad permission; remove this direct grant on the target item with operator approval'}
        if permission.get('view')=='metadata':
            return {'content_access':'UNKNOWN','reason':'Metadata view present but Limited Access/inheritance evidence is incomplete or contradictory'}
        if permission.get('role') in ('owner','organizer','fileOrganizer','writer','commenter','reader','publishedReader'):
            return {'content_access':'BROAD_CONTENT_OR_UNKNOWN','reason':'Broad permission has no proven metadata-only restriction'}
        return {'content_access':'UNKNOWN','reason':'Permission role is missing or unrecognized'}

    @classmethod
    def restricted_permissions(cls,metadata,permissions):
        if not permissions:return False
        return all(cls.classify_permission(metadata,p)['content_access'] in ('NAMED_USER','METADATA_ONLY') for p in permissions)

    def privacy(self):
        folder=self.settings.google_drive_folder_id
        visited=set();evidence=[]
        def check(file_id,is_target=False):
            if file_id in visited:raise DriveError('Không xác minh được cây quyền Drive.')
            visited.add(file_id);meta=self.metadata(file_id)
            if not meta or meta.get('trashed') or meta.get('mimeType')!='application/vnd.google-apps.folder':
                self.last_privacy_audit={'private':None,'access_verified':False,'folder_id':folder,
                    'blocked_item':file_id,'evidence':evidence,'reason':'Folder metadata is inaccessible or invalid; privacy and Editor access are UNVERIFIED, not confirmed public.'}
                raise DriveError('drive.file chưa được cấp quyền truy cập folder đích/cha. Cần Google Picker cùng OAuth project; không tự nâng scope.')
            permissions=self.permissions(file_id)
            assessed=[{'id':p.get('id'),'type':p.get('type'),'role':p.get('role'),'view':p.get('view'),
                       'permissionDetails':p.get('permissionDetails'),**self.classify_permission(meta,p)} for p in permissions]
            evidence.append({'file_id':file_id,'inheritedPermissionsDisabled':meta.get('inheritedPermissionsDisabled'),'permissions':assessed})
            self.last_privacy_audit={'private':False,'folder_id':folder,'evidence':evidence}
            if not self.restricted_permissions(meta,permissions):
                direct=[p for p in assessed if p['content_access']=='BROAD_CONTENT']
                if direct:
                    description=', '.join(f"{p['type']}:{p['role']} permission={p['id']}" for p in direct)
                    raise DriveError(f'Direct broad content grant trên folder {file_id}: {description}. Host cần xem Share/Manage access và bỏ direct grant trên đúng item nếu đồng ý. Không sửa permission thư mục cha tự động.')
                raise DriveError('Drive privacy chưa xác minh: có quyền nội dung rộng hoặc thiếu evidence Limited Access/view=metadata/inherited. Không upload. Kiểm tra audit; không tự sửa quyền folder cha.')
            if is_target and not meta.get('capabilities',{}).get('canAddChildren'):
                raise DriveError('OAuth chưa có quyền thêm file vào folder đích.')
            if meta.get('inheritedPermissionsDisabled') is not True:
                for parent in meta.get('parents',[]):check(parent)
        check(folder,True)
        self.last_privacy_audit={'private':True,'folder_id':folder,'evidence':evidence}
        return self.last_privacy_audit
    def reserve_id(self):
        return self.request('GET','drive/v3/files/generateIds',params={'count':1,'space':'drive','type':'files'}).json()['ids'][0]
    def upload(self,file_id,path,composite_id):
        # A reserved ID is committed locally before this call. On lost ACK,
        # the worker reads this same ID instead of creating another Drive file.
        existing=self.metadata(file_id)
        if existing:return existing
        body={'id':file_id,'name':'amazing-race-'+composite_id+'.png','mimeType':'image/png',
              'parents':[self.settings.google_drive_folder_id],'appProperties':{'photobooth_composite':composite_id}}
        boundary='photobooth-drive-upload'
        content=(f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode()+json.dumps(body).encode()+
                 f'\r\n--{boundary}\r\nContent-Type: image/png\r\n\r\n'.encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode())
        self.request('POST','upload/drive/v3/files',params={'uploadType':'multipart','supportsAllDrives':'true','fields':'id'},
                     headers={'Content-Type':'multipart/related; boundary='+boundary},content=content)
        return self.metadata(file_id)
    def download(self,file_id):
        response=self.request('GET','drive/v3/files/'+quote(file_id,safe=''),params={'alt':'media','supportsAllDrives':'true'})
        if response is None:raise DriveError('File Drive đã mất hoặc OAuth không còn quyền; không xóa cache.')
        return response.content
