"""Read operator-owned KEY=value files without shell execution/interpolation.

Exported environment overrides file values. CLI overrides both in run_host.py.
"""
import os
from pathlib import Path
import re
import json


def load_environment(path=None):
    values={}
    if path:
        for number,line in enumerate(Path(path).expanduser().read_text(encoding='utf-8-sig').splitlines(),1):
            line=line.strip()
            if not line or line.startswith('#'):continue
            name,separator,value=line.partition('=')
            name=name.strip();value=value.strip()
            if not separator or not re.fullmatch(r'[A-Z][A-Z0-9_]*',name):
                raise ValueError(f'Invalid environment configuration on line {number}; expected NAME=value')
            if value.startswith(('"',"'")):
                if len(value)<2 or value[-1]!=value[0]:raise ValueError(f'Unclosed quoted value on line {number}')
                value=value[1:-1]
            if '\x00' in value:raise ValueError(f'Invalid value on line {number}')
            if name in values:raise ValueError(f'Duplicate configuration variable {name}')
            values[name]=value
        # File paths are relative to that configuration file, independent of shell cwd.
        for name in ('OSA_STORAGE_ROOT','OSA_FRONTEND_DIST','OSA_LOG_DIRECTORY','HOST_SSL_CERTFILE','HOST_SSL_KEYFILE','PHOTOBOOTH_PYTHON'):
            if values.get(name):
                candidate=Path(values[name]).expanduser()
                values[name]=str((Path(path).expanduser().resolve().parent/candidate).resolve())
    return {**values,**os.environ}


def restore_drive_setting(env,storage_root):
    """Remember explicit storage opt-in per runtime; explicit config wins."""
    if 'GOOGLE_DRIVE_ENABLED' in env:return env
    path=Path(storage_root)/'.drive-config.json'
    if not path.exists():return env
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    if type(data.get('enabled')) is not bool:raise ValueError('Invalid persisted Drive setting')
    return {**env,'GOOGLE_DRIVE_ENABLED':str(data['enabled']).lower()}


def save_drive_setting(env,storage_root):
    if 'GOOGLE_DRIVE_ENABLED' not in env:return
    value=env['GOOGLE_DRIVE_ENABLED'].strip().lower()
    if value not in ('true','false'):raise ValueError('GOOGLE_DRIVE_ENABLED must be true or false')
    from app.services.images import atomic_write
    atomic_write(Path(storage_root)/'.drive-config.json',json.dumps({'enabled':value=='true'}).encode())
