# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import copy_metadata

# Get absolute paths - SPECPATH is the directory containing the spec file
PROJECT_ROOT = os.path.dirname(SPECPATH)

# Copy metadata for packages that need it
datas = []
try:
    datas += copy_metadata('textual')
except ImportError:
    pass
try:
    datas += copy_metadata('pyvisa-py')
except ImportError:
    pass
try:
    datas += copy_metadata('textual-plotext')
except ImportError:
    pass
try:
    datas += copy_metadata('textual-image')
except ImportError:
    pass

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'src', 'tina', 'main.py')],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'pyvisa-py',
        'textual',
        'textual.app',
        'textual.widgets',
        'textual_plotext',
        'textual_image',
        'textual_image.widget',
        'matplotlib',
        'matplotlib.pyplot',
        'numpy',
        'skrf',
        'platformdirs',
        'queue',
        'threading',
        'asyncio',
        'tina.config.constants',
        'tina.config.settings',
        'tina.drivers',
        'tina.drivers.base',
        'tina.drivers.hp_e5071b',
        'tina.drivers.scpi_commands',
        'tina.utils',
        'tina.utils.colors',
        'tina.utils.terminal',
        'tina.utils.paths',
        'tina.utils.touchstone',
        'tina.worker',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'test',
        'tests',
        'pydoc',
        'doctest',
        'xmlrpc',
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
    name='tina',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJECT_ROOT, 'res', 'icon.ico'),
    distpath='dist',
)
