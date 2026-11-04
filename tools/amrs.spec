# PyInstaller build recipe. Windows supplies the unversioned ICU API used by Qt.
import json
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all,collect_submodules,copy_metadata

root=Path(SPECPATH).parent
models=json.loads((root/'models'/'manifest.json').read_text())['models']
datas=[(str(root/'db'/'schema'),'db/schema'),(str(root/'models'/'manifest.json'),'models'),(os.environ['AMRS_BUILD_MANIFEST'],'.')]
datas += [(str(root/'models'/model['filename']),'models') for model in models]
datas += [(str(root/'amrs'/'qr_assets'),'amrs/qr_assets')]
cv_data,cv_binaries,cv_imports=collect_all('cv2')
datas += cv_data
for line in (root/'requirements.lock.txt').read_text().splitlines():
    if '==' in line and not line.startswith('#'):datas += copy_metadata(line.split('==',1)[0])

a=Analysis([str(root/'main.py')],pathex=[str(root)],binaries=cv_binaries,datas=datas,hiddenimports=collect_submodules('amrs')+collect_submodules('oracledb')+cv_imports,hookspath=[],hooksconfig={},runtime_hooks=[],excludes=[],noarchive=False,optimize=0)
# Do not bundle unrelated ICU builds found in developer tools on PATH. Their
# renamed exports break QtCore. Qt on the supported Windows target uses the OS
# unversioned ICU library. No Windows file is copied, replaced or modified.
a.binaries=[entry for entry in a.binaries if Path(entry[0]).name.lower() not in {'icuuc.dll','icuin.dll','icudt.dll'}]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='AMRS',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='AMRS')
