# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

block_cipher = None

extra_datas = [
    ("HouRM_icon.png", "."),
    ("HouRM_icon.ico", "."),
    ("render_rop.py", "."),
    ("scan_rops.py", "."),
    ("config.example.json", "."),
]
extra_binaries = []
hiddenimports = [
    "PIL",
    "PIL.Image",
    "numpy",
    "cv2",
    "frame_preview",
    "app_paths",
]

for pkg in ("PIL", "numpy", "cv2"):
    try:
        datas, binaries, hidden = collect_all(pkg)
        extra_datas += datas
        extra_binaries += binaries
        hiddenimports += hidden
    except Exception:
        pass

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=extra_binaries,
    datas=extra_datas,
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
    name="HoudiniRenderManager",
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
    icon="HouRM_icon.ico",
)
