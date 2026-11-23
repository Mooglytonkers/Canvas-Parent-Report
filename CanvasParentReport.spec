# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows desktop app (one folder, wrapped by Inno Setup)."""

from PyInstaller.utils.hooks import collect_submodules

hidden = []
for package in ("keyring.backends", "reportlab"):
    try:
        hidden.extend(collect_submodules(package))
    except Exception:
        pass

a = Analysis(
    ["desktop_app.py"],
    pathex=["."],
    binaries=[],
    datas=[("assets/icon.ico", "assets"), ("assets/icon.png", "assets")],
    hiddenimports=hidden
    + [
        "desktop",
        "desktop.app",
        "desktop.runner",
        "desktop.wizard",
        "desktop.main_window",
        "keyring.backends.Windows",
        "report_pdf",
        "reportlab.pdfgen",
        "reportlab.platypus",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["weasyprint", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CanvasParentReport",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon="assets/icon.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CanvasParentReport",
)
