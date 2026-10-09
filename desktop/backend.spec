# Build with scripts/build-desktop.cjs so outputs land under build/backend.
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata


root = Path(SPECPATH).parent

analysis = Analysis(
    [str(root / "desktop" / "backend-entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "fpv_audio_pairing" / "static"), "fpv_audio_pairing/static")]
    + copy_metadata("fpv-audio-pairing"),
    # Uvicorn loads these by name. NumPy/SciPy's native libraries are collected
    # by the standard PyInstaller hooks as their imports are analyzed.
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [("u", None, "OPTION"), ("X utf8", None, "OPTION")],
    exclude_binaries=True,
    name="flight-sync-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="flight-sync-backend",
)
