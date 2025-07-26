# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

project_root = os.path.abspath(r"C:\Users\abdal\PycharmProjects\MetPlot")

hiddenimports = collect_submodules('pyproj') 
hiddenimports += collect_submodules('nicegui')  

datas = collect_data_files('nicegui') + collect_data_files('pyproj') + [
    (r'C:\Users\abdal\PycharmProjects\MetPlot\GUI\templates', 'templates')
]

a = Analysis(
    ['GUI\\main.py'],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='main',
)
