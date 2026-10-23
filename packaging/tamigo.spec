# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec. Pokreće se samo na macOS, iz scripts/build_macos_app.sh."""

from PyInstaller.utils.hooks import collect_all, collect_submodules

pyside_datas, pyside_binaries, pyside_hidden = collect_all("PySide6")

block_cipher = None

a = Analysis(
    ["launch_tamigo.py"],
    pathex=["."],
    binaries=pyside_binaries,
    datas=pyside_datas,
    hiddenimports=collect_submodules("tamigo_intel") + pyside_hidden + ["pypdf"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Tamigo Accessibility Intelligence",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Tamigo Accessibility Intelligence",
)
app = BUNDLE(
    coll,
    name="Tamigo Accessibility Intelligence.app",
    bundle_identifier="pro.tamigo.accessibility-intelligence",
    info_plist={
        "CFBundleName": "Tamigo Accessibility Intelligence",
        "CFBundleDisplayName": "Tamigo Accessibility Intelligence",
        "CFBundleShortVersionString": "0.2.0",
        "CFBundleVersion": "0.2.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
    },
)
