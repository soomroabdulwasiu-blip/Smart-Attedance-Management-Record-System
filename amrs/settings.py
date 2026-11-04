"""Small local preferences. No face images or credentials are stored here."""
import json,os,uuid
from pathlib import Path
from .paths import DATA_ROOT

SETTINGS_PATH=DATA_ROOT/'ui_settings.json'

def mirror_preview_enabled():
    try:
        data=json.loads(SETTINGS_PATH.read_text(encoding='utf-8'))
        value=data.get('mirror_preview',True)
        return value if isinstance(value,bool) else True
    except (OSError,ValueError,TypeError,AttributeError):
        return True

def save_mirror_preview(enabled):
    SETTINGS_PATH.parent.mkdir(parents=True,exist_ok=True)
    try:
        data=json.loads(SETTINGS_PATH.read_text(encoding='utf-8'))
        if not isinstance(data,dict):data={}
    except (OSError,ValueError,TypeError):data={}
    data['mirror_preview']=bool(enabled)
    tmp=SETTINGS_PATH.with_name(SETTINGS_PATH.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        tmp.write_text(json.dumps(data,indent=2),encoding='utf-8')
        os.replace(tmp,SETTINGS_PATH)
    finally:
        tmp.unlink(missing_ok=True)
