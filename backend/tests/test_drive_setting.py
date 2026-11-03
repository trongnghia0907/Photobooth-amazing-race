import sys
from pathlib import Path
from dataclasses import replace
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from host_environment import restore_drive_setting,save_drive_setting
from test_drive_storage import setup,confirmed

def test_drive_opt_in_survives_restart_and_is_scoped_to_runtime(tmp_path):
    active=tmp_path/'active';active.mkdir();other=tmp_path/'other';other.mkdir()
    assert restore_drive_setting({},active)=={}
    save_drive_setting({'GOOGLE_DRIVE_ENABLED':'true'},active)
    assert restore_drive_setting({},active)['GOOGLE_DRIVE_ENABLED']=='true'
    assert restore_drive_setting({},other)=={}
    assert restore_drive_setting({'GOOGLE_DRIVE_ENABLED':'false'},active)['GOOGLE_DRIVE_ENABLED']=='false'
    save_drive_setting({'GOOGLE_DRIVE_ENABLED':'false'},active)
    assert restore_drive_setting({},active)['GOOGLE_DRIVE_ENABLED']=='false'

@pytest.mark.parametrize('consent',[False,None])
def test_no_publication_consent_does_not_block_private_upload(setup,consent):
    client,repo,fake,settings=setup
    repo.settings=replace(settings,event_gallery_auto_publish=True)
    original=repo.upload_composite
    def upload(*args):
        values=list(args);values[4]=dict(values[4])
        if consent is False:values[4]['event_display_consent']=False
        return original(*values)
    repo.upload_composite=upload
    sid,cid=confirmed(client,4)
    with repo.db.connect() as db:
        assert db.execute('SELECT state FROM drive_uploads WHERE composite_id=?',(cid,)).fetchone()[0]=='PENDING'
        assert db.execute('SELECT COUNT(*) FROM event_display_photos WHERE session_id=?',(sid,)).fetchone()[0]==0
    fake.offline=True;repo.drive.process_one()
    assert (settings.storage_root/f'composites/{sid}/{cid}.png').is_file()
    fake.offline=False;repo.drive.retry();repo.drive.process_one()
    assert repo.drive.ready(cid) and len(fake.files)==1
