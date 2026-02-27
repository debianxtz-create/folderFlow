# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('folderFlow-icon.png', '.'), ('credentials.json', '.')]
binaries = []
hiddenimports = ['PyQt6.sip', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'google.auth.transport.requests', 'google.oauth2.credentials', 'google_auth_oauthlib.flow', 'googleapiclient.discovery', 'googleapiclient._helpers', 'googleapiclient.http', 'src.paths', 'src.config', 'src.auth', 'src.engine', 'src.scheduler', 'src.tracker']
tmp_ret = collect_all('PyQt6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('google_auth_oauthlib')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('googleapiclient')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('google.auth')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
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
    a.binaries,
    a.datas,
    [],
    name='FolderFlow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['folderFlow-icon.png'],
)
