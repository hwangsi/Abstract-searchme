# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for AbstractSearcher (onefile / windowed)
# Run from project root: pyinstaller build/abstract_searcher.spec --clean --noconfirm

import os
from PyInstaller.utils.hooks import collect_all

# SPECPATH is the directory containing this spec file (build/).
# ROOT is the project root (one level up).
ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

# Collect pymupdf: includes mupdfcpp64.dll + _extra.pyd/_mupdf.pyd binaries
pymupdf_datas, pymupdf_binaries, pymupdf_hidden = collect_all('pymupdf')

# Collect ics: has many submodule hidden imports + data files
ics_datas, ics_binaries, ics_hidden = collect_all('ics')

a = Analysis(
    [os.path.join(ROOT, 'desktop', 'main.py')],
    pathex=[ROOT],
    binaries=pymupdf_binaries + ics_binaries,
    datas=pymupdf_datas + ics_datas,
    hiddenimports=[
        # PySide6 — explicitly include core modules auto-detect sometimes misses
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        # PDF library (fitz is a thin wrapper re-exporting pymupdf)
        'fitz',
        'pymupdf',
        # Workers use dynamic imports — must be listed explicitly
        'core.main',
        'core.adapters.kcr',
        'core.adapters.icr',
        'core.adapters.gbcc',
        'core.adapters.generic',
        'core.search.matcher',
        'core.exporters.text_exporter',
        'core.exporters.xlsx_exporter',
        'core.exporters.ics_exporter',
        # Libraries
        'rapidfuzz',
        'rapidfuzz.fuzz',
        'rapidfuzz.process',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'difflib',
    ] + pymupdf_hidden + ics_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Unused PySide6 subsystems (large)
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineQuick',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DRender',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic',
        'PySide6.Qt3DAnimation',
        'PySide6.Qt3DExtras',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtNetworkAuth',
        'PySide6.QtPositioning',
        'PySide6.QtSensors',
        'PySide6.QtBluetooth',
        'PySide6.QtSerialPort',
        'PySide6.QtRemoteObjects',
        'PySide6.QtDesigner',
        'PySide6.QtHelp',
        'PySide6.QtTest',
        # Other unused heavy packages
        'matplotlib',
        'scipy',
        'tkinter',
        'PyQt5',
        'PyQt6',
        'wx',
        'gi',
        'gtk',
        'IPython',
        'jupyter',
        'notebook',
        'sphinx',
        'docutils',
        'PIL',
        'cv2',
    ],
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
    name='AbstractSearcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
    # icon='build/app.ico',  # uncomment when .ico is ready
)
