# PyInstaller's folder distribution keeps Qt DLLs replaceable and starts
# without extracting a full Qt runtime on every launch.
from pathlib import Path
import sys

root = Path(SPECPATH)
analysis = Analysis(
    [str(root / 'run.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / 'resources'), 'resources')],
    hiddenimports=['pygame._sdl2.controller'],
    hookspath=[],
    excludes=['PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtWebEngineCore', 'tkinter'],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [],
    exclude_binaries=True,
    name='BloodPSPLauncher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(root / 'resources' / 'app.ico'),
)
distribution = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name='BloodPSPLauncher')
