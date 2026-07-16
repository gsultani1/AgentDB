# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the self-contained swadb sidecar (onedir).

Build via sidecar/build-sidecar.sh (which prepares build/hf-cache first).
onedir, not onefile: onefile would extract >1GB (torch) on every cold
start. The archive contract consumed by fable-ide:
  swadb-sidecar/            <- COLLECT output dir
    swadb[.exe]             <- launcher
    _internal/
      hf-cache/hub/...      <- bundled embedding model (offline)
      swadb/static/...      <- web UI
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("torch", "transformers", "tokenizers", "safetensors"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# sentence_transformers loads module classes from strings in modules.json.
hiddenimports += collect_submodules("sentence_transformers")

# swadb itself: editable installs (pip install -e ..) expose the package
# through a PEP-660 finder PyInstaller can't trace — pathex makes the repo
# root visible as a plain source tree and the explicit submodule list
# guarantees every swadb module lands in the bundle.
hiddenimports += collect_submodules("swadb")

hiddenimports += [
    # MCP SSE auto-starts inside `serve` (mcp_enabled defaults true) —
    # uvicorn/starlette resolve protocols dynamically; keep ALL of these.
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
    "mcp.server.fastmcp", "sse_starlette", "starlette",
    "hnswlib",
]

datas += [
    ("../swadb/static", "swadb/static"),     # server serves Path(__file__).parent/"static"
    ("build/hf-cache/hub", "hf-cache/hub"),  # produced by prepare_hf_cache.py
]

a = Analysis(
    ["sidecar_entry.py"],
    pathex=[".."],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=[
        "pip", "setuptools", "pytest", "_pytest", "typer", "rich",
        "shellingham", "pygments", "tkinter", "IPython", "matplotlib",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    name="swadb",
    console=True,
    exclude_binaries=True,
    upx=False,
)
COLLECT(exe, a.binaries, a.datas, name="swadb-sidecar", upx=False)
