"""Desktop Picker flow only. Dummy credentials; no Google/browser network."""
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs,urlsplit

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from google_drive_picker import FolderPickerFlow,client_configuration,validate_selection,authorize_folder
from app.config import Settings
from app.services.drive_client import GoogleDriveClient,DriveError,SCOPE

TARGET='1ixmork-KFJ8xdtQCFJIpUTQm-SnJqeez'
DUMMY={'client_id':'123-dummy.apps.googleusercontent.com','client_secret':'dummy-only',
       'refresh_token':'dummy-refresh','token_uri':'https://oauth2.googleapis.com/token','scopes':[SCOPE]}


class Store:
    def load(self):return json.dumps(DUMMY)


def test_existing_project_client_and_native_picker_parameters():
    config,_=client_configuration(Store())
    assert config['installed']['client_id']==DUMMY['client_id']
    flow=FolderPickerFlow.from_client_config(config,[SCOPE],autogenerate_code_verifier=True)
    flow.redirect_uri='http://127.0.0.1:12345/'
    url,_=flow.authorization_url(prompt='consent',trigger_onepick='true',file_ids=TARGET,
        allow_folder_selection='true',allow_multiple='false',include_granted_scopes='false')
    query=parse_qs(urlsplit(url).query)
    assert query['scope']==[SCOPE]
    assert query['trigger_onepick']==['true'] and query['file_ids']==[TARGET]
    assert query['allow_folder_selection']==['true'] and query['allow_multiple']==['false']
    assert query['code_challenge'] and query['state'] and query['include_granted_scopes']==['false']


@pytest.mark.parametrize('selection',['','other',TARGET+',other',TARGET+','+TARGET])
def test_missing_cancelled_or_wrong_folder_cannot_replace_credentials(selection):
    with pytest.raises(DriveError):validate_selection('https://127.0.0.1/?picked_file_ids='+selection,TARGET)


def test_exact_selection_continues_standard_oauth_code_exchange_and_state_check(monkeypatch):
    config,_=client_configuration(Store());flow=FolderPickerFlow.from_client_config(config,[SCOPE])
    flow.target_folder=TARGET;calls=[]
    monkeypatch.setattr('google_auth_oauthlib.flow.InstalledAppFlow.fetch_token',lambda self,**kwargs:calls.append(kwargs))
    callback='https://127.0.0.1/?picked_file_ids='+TARGET+'&code=dummy&state=dummy'
    flow.fetch_token(authorization_response=callback)
    assert calls==[{'authorization_response':callback,'timeout':45}]


def test_different_project_client_is_rejected(tmp_path):
    config,_=client_configuration(Store());config['installed']['client_id']='another-project'
    path=tmp_path/'client.json';path.write_text(json.dumps(config))
    with pytest.raises(DriveError,match='differs'):client_configuration(Store(),path)


def test_missing_folder_access_does_not_claim_public_sharing(tmp_path):
    client=GoogleDriveClient(Settings(tmp_path))
    client.metadata=lambda file_id:None
    with pytest.raises(DriveError):client.privacy()
    assert client.last_privacy_audit['private'] is None
    assert client.last_privacy_audit['access_verified'] is False
    assert client.last_privacy_audit['blocked_item']==TARGET


@pytest.mark.parametrize('granted,refresh,success',[
    ([SCOPE,'https://www.googleapis.com/auth/drive'],'dummy-refresh',False),
    ([SCOPE],None,False),
    ([SCOPE],'dummy-refresh',True),
])
def test_only_narrow_scope_with_offline_authorization_is_saved(tmp_path,monkeypatch,granted,refresh,success):
    import google_drive_picker as picker
    from types import SimpleNamespace
    written=[];options=[]
    class SavedStore(Store):
        def save(self,value):written.append(value)
    dummy=SimpleNamespace(granted_scopes=granted,scopes=[SCOPE],refresh_token=refresh,to_json=lambda:json.dumps(DUMMY))
    class Flow:
        def run_local_server(self,**kwargs):options.append(kwargs);return dummy
    monkeypatch.setattr(picker,'CredentialStore',lambda root:SavedStore())
    monkeypatch.setattr(picker.FolderPickerFlow,'from_client_config',lambda *args,**kwargs:Flow())
    settings=Settings(tmp_path)
    if success:
        authorize_folder(settings)
        assert written==[json.dumps(DUMMY)]
    else:
        with pytest.raises(DriveError):authorize_folder(settings)
        assert written==[]
    assert options[0]['trigger_onepick']=='true' and options[0]['prompt']=='consent'
    assert options[0]['allow_folder_selection']=='true'
    assert 'mimetypes' not in options[0] and 'file_ids' not in options[0]
