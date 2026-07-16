# swadb sidecar — self-contained binary

PyInstaller onedir bundle of the swadb server for embedding into desktop
apps (fable-ide's Theia electron app bundles it under
`resources/swadb-sidecar/`). No Python required on the user's machine;
the embedding model (all-MiniLM-L6-v2) ships inside, so memory works
fully offline out of the box.

## Contract (consumed by fable-ide)

- Release asset name: `swadb-sidecar-v<version>-<os>-<arch>.tar.gz`
  (`.zip` on Windows). `<os>` uses Node `process.platform` values
  (`linux` | `darwin` | `win32`); `<arch>` is `x64` | `arm64`.
- Archive contains one top-level dir `swadb-sidecar/` with the launcher
  `swadb-sidecar/swadb` (`swadb.exe` on Windows). The bundled model cache
  lives at `swadb-sidecar/_internal/hf-cache/hub`.
- Behavior: `<bin> --db <path> init` exits 0; `<bin> --db <path> serve
  --host H --port P` serves the HTTP API (default 8420) and the embedded
  MCP SSE server (8421); `memory add` / `memory search` work offline.

## Build

```bash
# Linux: install CPU-only torch FIRST — the default PyPI wheel bundles
# the CUDA stack (~2.5 GB of nvidia_* libs), which collect_all("torch")
# would drag into the bundle and blow past GitHub's 2 GiB release-asset
# limit. (Mac wheels are CPU/MPS-only; Windows PyPI wheels are CPU.)
pip install torch --index-url https://download.pytorch.org/whl/cpu

pip install -e ..            # swadb + runtime deps in the build env
bash build-sidecar.sh        # prepares hf cache, runs PyInstaller, tars
```

CI (`.github/workflows/sidecar.yml`) builds per-OS on release tags and
attaches the archives to the GitHub Release. Builds are unsigned in v1 —
macOS Gatekeeper quarantines downloaded unsigned binaries
(`xattr -dr com.apple.quarantine` or distribution inside a signed app
bundle sidesteps it).

## Scope decisions (v1)

- **onedir, not onefile** — onefile would re-extract >1 GB (torch) on
  every cold start.
- **hnswlib: bundled** (built with `HNSWLIB_NO_NATIVE=1` for portability)
  — ANN acceleration works out of the box.
- **sqlcipher3, pdfminer.six: omitted** — at-rest encryption and PDF
  ingestion remain pip-install-only features.
- **Reranker cross-encoder: omitted** (~90 MB, `reranker_enabled`
  defaults false, retrieval degrades gracefully). Enabling the reranker
  against the sidecar offline is a no-op.
- **No sklearn/scipy exclusion** — sentence-transformers pulls them in;
  excluding (~190 MB) is untested against frozen encode paths. Revisit.
- **Python skills in packaged mode** need a system `python3`/`python` on
  PATH (`swadb/pyexec.py`); without one they return a readable error.
  Bash skills are unaffected.
- **`SWADB_EMBED_DEVICE`** forces the torch device for the embedding
  model (unset = auto). CI sets `cpu` everywhere: GitHub's arm64 macOS
  runners expose an MPS pool so small that loading the model OOMs. End
  users on real Macs get MPS/auto by default.

## Size / startup (Linux x64, CPU torch)

~1.1–1.3 GB unpacked, ~350–450 MB tar.gz (torch dominates; the model
cache is ~88 MB). Cold start 2–6 s (torch import). A future
onnxruntime-based embedding path could drop ~700 MB.
