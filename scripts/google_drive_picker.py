"""Desktop Picker authorization with the saved project's drive.file client.

Google's OAuth-hosted Picker returns picked_file_ids through the normal PKCE
loopback callback. No API key, web client, access token in HTML, or sharing write.
"""
import json
from urllib.parse import parse_qs, urlsplit

from google_auth_oauthlib.flow import InstalledAppFlow
from google_auth_oauthlib.flow import WSGITimeoutError
from oauthlib.oauth2 import OAuth2Error

from app.services.drive_client import CredentialStore, DriveError, SCOPE


def validate_selection(response, target):
    query=parse_qs(urlsplit(response).query)
    selected=query.get('picked_file_ids',[])
    if not selected:
        raise DriveError('Callback did not include picked_file_ids. Folder selection was not confirmed. Reopen --pick-folder, enable Google Picker API in the same Cloud project if needed, and let Google redirect after Insert; do not open the callback URL directly. Saved credentials were not replaced.')
    if len(selected)!=1 or selected[0].split(',')!=[target]:
        raise DriveError('Picker did not select exactly the approved target folder. Saved credentials were not replaced; select the target folder and confirm Insert.')


class FolderPickerFlow(InstalledAppFlow):
    def authorization_url(self,**kwargs):
        url,state=super().authorization_url(**kwargs)
        query=parse_qs(urlsplit(url).query)
        print(json.dumps({'picker_parameters':{key:query.get(key) for key in
            ('trigger_onepick','prompt','allow_folder_selection','scope')}}),flush=True)
        return url,state

    def fetch_token(self, **kwargs):
        validate_selection(kwargs.get('authorization_response',''),self.target_folder)
        kwargs.setdefault('timeout',45)
        print('Approved folder received from Picker; exchanging the authorization code.',flush=True)
        return super().fetch_token(**kwargs)


def client_configuration(store, client_file=None):
    saved=None
    try:saved=json.loads(store.load())
    except DriveError:
        if client_file is None or not client_file.is_file():raise
    if client_file is not None and client_file.is_file():
        config=json.loads(client_file.read_text(encoding='utf-8-sig'))
        installed=config.get('installed',{})
        if not installed.get('client_id') or not installed.get('client_secret'):
            raise DriveError('Picker requires the existing Desktop OAuth client JSON (installed application type).')
        if saved and installed['client_id']!=saved.get('client_id'):
            raise DriveError('OAuth client differs from the saved project. Use the original Desktop OAuth client; credentials were not changed.')
    else:
        if not saved or not saved.get('client_id') or not saved.get('client_secret'):
            raise DriveError('Saved Desktop OAuth client is unavailable. Supply its original JSON with --client-file.')
        installed={'client_id':saved['client_id'],'client_secret':saved['client_secret'],
                   'auth_uri':'https://accounts.google.com/o/oauth2/auth',
                   'token_uri':'https://oauth2.googleapis.com/token','redirect_uris':['http://localhost']}
        config={'installed':installed}
    # Never allow a supplied JSON to redirect the authorization code or secret.
    if installed.get('auth_uri') not in ('https://accounts.google.com/o/oauth2/auth','https://accounts.google.com/o/oauth2/v2/auth') or installed.get('token_uri')!='https://oauth2.googleapis.com/token':
        raise DriveError('OAuth client must use the official Google authorization/token endpoints.')
    return config,saved


def authorize_folder(settings,client_file=None):
    store=CredentialStore(settings.storage_root)
    config,_=client_configuration(store,client_file)
    flow=FolderPickerFlow.from_client_config(config,[SCOPE],autogenerate_code_verifier=True)
    flow.target_folder=settings.google_drive_folder_id
    print('Google Picker is opening. Select the approved folder and confirm Insert. If Google requests API setup, enable Google Picker API in the SAME Cloud project as the existing Desktop OAuth client.',flush=True)
    try:
        credentials=flow.run_local_server(host='127.0.0.1',port=0,access_type='offline',prompt='consent',
            trigger_onepick='true',allow_folder_selection='true',allow_multiple='false',
            include_granted_scopes='false',timeout_seconds=300,
            authorization_prompt_message='Complete the folder selection in the browser. No tokens are printed.',
            success_message='Google returned to Photobooth. Check the terminal for selection, access and privacy results.')
    except WSGITimeoutError:
        raise DriveError('Picker timed out. Saved credentials were not replaced; run --pick-folder again and complete the browser selection.') from None
    except OAuth2Error as error:
        raise DriveError(f'Google Picker authorization failed ({error.error}). Enable Google Picker API in the existing OAuth project, check the consent/test-user setup, then retry. Saved credentials were not replaced.') from None
    if set(credentials.granted_scopes or credentials.scopes or [])!={SCOPE}:
        raise DriveError('Unexpected OAuth scope returned. Saved credentials were not replaced.')
    if not credentials.refresh_token:
        raise DriveError('Google did not grant offline access. Saved credentials were not replaced; repeat consent.')
    store.save(credentials.to_json())
    print('Picker selected the exact target. OAuth credentials saved with OS protection.',flush=True)
