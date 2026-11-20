# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

project_root = Path(os.getcwd()).resolve()
gui_dir = project_root / 'GUI'

hiddenimports = []
hiddenimports += collect_submodules('pyproj')
hiddenimports += collect_submodules('nicegui')
hiddenimports += collect_submodules('matplotlib.backends')
hiddenimports += collect_submodules('cfgrib')
hiddenimports += [
    'eccodes',
    'gribapi',
    'xarray',
    'netCDF4',
    'cftime',
    'pandas',
    'cv2',
    'PIL',
    'modeldownloads',
    'plotting_backend',
    'EventBus_Observers',
]

datas = []
datas += collect_data_files('nicegui')
datas += collect_data_files('pyproj')
datas += collect_data_files('cfgrib')
datas += collect_data_files('eccodes')
datas += [
    (str(gui_dir / 'templates'), 'templates'),
    (str(project_root / 'MetPlot' / 'Variables'), 'MetPlot/Variables'),
]

# OS-specific wgrib2 binaries / DLLs
wgrib_dir = project_root / 'MetPlot' / 'wgrib'
if sys.platform == 'win32':
    if (wgrib_dir / 'wgrib2.exe').exists():
        datas.append((str(wgrib_dir / 'wgrib2.exe'), 'MetPlot/wgrib'))
    for dll in wgrib_dir.glob('*.dll'):
        datas.append((str(dll), 'MetPlot/wgrib'))
else:
    if (wgrib_dir / 'wgrib2').exists():
        datas.append((str(wgrib_dir / 'wgrib2'), 'MetPlot/wgrib'))

# Bundle conda eccodes definitions if present so cfgrib works in frozen builds
prefix = Path(sys.prefix)
for rel in ('Library/share/eccodes', 'share/eccodes'):
    ecc_share = prefix / rel
    if ecc_share.is_dir():
        datas.append((str(ecc_share), 'share/eccodes'))
        break

a = Analysis(
    [str(gui_dir / 'main.py')],
    pathex=[str(project_root), str(gui_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pygrib'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MetPlot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MetPlot',
)
