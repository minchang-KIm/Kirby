# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

spec_location = Path(SPECPATH).resolve()
root = spec_location.parent if spec_location.is_dir() else spec_location.parent.parent
entry = root / Path("windsprig/__main__.py")
datas = [
    (str(root / Path("windsprig/content")), "windsprig/content"),
    (str(root / "assets"), "assets"),
    (str(root / "LICENSE"), "."),
    (str(root / "CREDITS.md"), "."),
]

a = Analysis(
    [str(entry)],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=["pygame"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["hypothesis", "mypy", "playwright", "pygbag", "pytest", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Windsprig",
    console=False,
    icon=str(root / Path("assets/branding/windsprig.ico")),
    version=str(root / Path("packaging/version_info.txt")),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Windsprig",
)
