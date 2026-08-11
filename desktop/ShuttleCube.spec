from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).resolve().parent
hiddenimports = collect_submodules("webview.platforms") + [
    "shuttlecube.domain.models",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

a = Analysis(
    [str(root / "backend" / "src" / "shuttlecube" / "desktop.py")],
    pathex=[str(root / "backend" / "src")],
    binaries=[],
    datas=[
        (str(root / "frontend" / "dist"), "frontend_dist"),
        (str(root / "backend" / "alembic"), "backend_resources/alembic"),
        (str(root / "backend" / "alembic.ini"), "backend_resources"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "mypy", "hypothesis", "testcontainers"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ShuttleCube",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="ShuttleCube",
)
