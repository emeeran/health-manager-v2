# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec for the desktop sidecar.

onedir, NOT onefile (onefile re-extracted ~80 MB to /tmp on every launch
upstream). Bundled data: built SPA → _MEIPASS/frontend; prompts/;
alembic/ + alembic.ini (boot runs `alembic upgrade head`, %(here)s
relative); pyproject.toml (APP_VERSION). Hidden imports: mako/markupsafe
(alembic ≥1.18 template engine — without them the frozen app dies with
bare exit 3) and lazy SQLAlchemy/uvicorn/fastapi submodules.
"""

import os
from pathlib import Path

ROOT = Path(SPECPATH)
FRONTEND_DIST = ROOT.parent / "frontend" / "dist"
if not (FRONTEND_DIST / "index.html").is_file():
    raise SystemExit(
        f"Frontend not built: {FRONTEND_DIST} missing. "
        "Run `cd frontend && npm run build` first."
    )

# pymupdf 2.x auto-activates its layout analyzer, which loads an ONNX
# config from site-packages at import — collect it.
import pymupdf  # noqa: E402

PYMUPDF_RESOURCES = Path(pymupdf.__file__).parent / "layout" / "resources"

a = Analysis(
    ["desktop_main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(FRONTEND_DIST), "frontend"),
        (str(ROOT.parent / "prompts"), "prompts"),
        (str(ROOT / "alembic"), "alembic"),
        (str(ROOT / "alembic.ini"), "."),
        (str(ROOT / "pyproject.toml"), "."),
        # Bundled reference data: CDC growth CSVs (growth_service fail-fasts
        # at import without them) + Jan Aushadhi catalog. Loaders resolve
        # Path(__file__)/…/data, which lands at _MEIPASS/app/data when frozen.
        (str(ROOT / "app" / "data"), "app/data"),
        (str(PYMUPDF_RESOURCES), "pymupdf/layout/resources"),
    ],
    hiddenimports=[
        "mako",
        "markupsafe",
        "passlib.handlers.argon2",
        "sqlalchemy.dialects.sqlite",
        "uvicorn.logging",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.web.websockets_impl",
        "uvicorn.lifespan.on",
        "aiosqlite",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "app.scripts",
        "pytest",
        "tkinter",
        "mypy",
        "ruff",
        "pip",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="health-manager-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="health-manager-backend",
)
