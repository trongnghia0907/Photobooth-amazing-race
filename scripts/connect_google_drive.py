"""Explicit operator login. No uploads or Drive permission changes."""
import argparse
import json
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
from host_environment import load_environment
from app.config import Settings
from app.services.drive_client import CredentialStore,GoogleDriveClient,DriveError,SCOPE

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path)
    parser.add_argument('--check',action='store_true',help='Check existing OAuth/privacy only, no browser login')
    parser.add_argument('--storage-root',type=Path)
    parser.add_argument('--client-file',type=Path)
    parser.add_argument('--audit',action='store_true',help='Read raw privacy evidence with existing OAuth; never opens login or changes permissions')
    parser.add_argument('--pick-folder',action='store_true',help='Open Google OAuth Desktop Picker with the existing project and select only the approved destination')
    parser.add_argument('--test-upload',action='store_true',help='Upload/reuse ONE disposable test image only after authenticated privacy checks pass')
    args=parser.parse_args()
    if args.pick_folder and (args.check or args.audit):parser.error('--pick-folder cannot be combined with read-only --check/--audit')
    import os
    os.environ.update(load_environment(args.env_file))
    if args.storage_root:os.environ['OSA_STORAGE_ROOT']=str(args.storage_root.resolve())
    if args.client_file:os.environ['GOOGLE_OAUTH_CLIENT_FILE']=str(args.client_file.resolve())
    settings=Settings.from_environment()
    if args.pick_folder:
        from google_drive_picker import authorize_folder
        authorize_folder(settings,settings.google_oauth_client_file)
    elif not (args.check or args.audit):
        client_file=settings.google_oauth_client_file or root/'.tools/google-drive/client_secret.json'
        if not client_file.is_file():raise DriveError('Missing Desktop OAuth client JSON. Enable Drive API and place client JSON in .tools/google-drive/client_secret.json or GOOGLE_OAUTH_CLIENT_FILE.')
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow=InstalledAppFlow.from_client_secrets_file(str(client_file),[SCOPE],autogenerate_code_verifier=True)
        credentials=flow.run_local_server(host='127.0.0.1',port=0,access_type='offline',prompt='consent',timeout_seconds=180)
        settings.storage_root.mkdir(parents=True,exist_ok=True)
        CredentialStore(settings.storage_root).save(credentials.to_json())
    client=GoogleDriveClient(settings)
    try:result=client.privacy()
    except DriveError:
        if args.audit or args.pick_folder:
            print(json.dumps(getattr(client,'last_privacy_audit',{'private':None,'reason':'Authenticated folder/permission evidence unavailable; access and privacy are UNVERIFIED.'}),indent=2))
        raise
    print(json.dumps(result))
    if args.test_upload:
        from app.services.repository import Repository
        import hashlib
        repo=Repository(settings);repo.drive.test_upload()
        with repo.db.connect() as db:file_id=db.execute("SELECT value FROM host_settings WHERE key='drive:test-id'").fetchone()[0]
        meta=client.metadata(file_id);data=(settings.storage_root/'.drive-test.png').read_bytes()
        if not meta or meta.get('id')!=file_id or int(meta.get('size',-1))!=len(data) or meta.get('md5Checksum')!=hashlib.md5(data).hexdigest():
            raise DriveError('Disposable upload metadata verification failed. Local test data retained.')
        print(json.dumps({'test_upload':'VERIFIED','file_id':file_id,'size':int(meta['size']),'folder_id':settings.google_drive_folder_id}))
    else:print('No photo was uploaded. If folder access is missing, run this script with --pick-folder using the existing OAuth project.')

if __name__=='__main__':
    try:main()
    except ImportError:raise SystemExit('Install backend/requirements-drive-optional.txt before OAuth login.')
    except DriveError as error:raise SystemExit(str(error))
