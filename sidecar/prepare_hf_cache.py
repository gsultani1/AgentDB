"""
Build the bundled HuggingFace model cache for the sidecar.

Produces sidecar/build/hf-cache/hub containing the embedding model
(all-MiniLM-L6-v2) with snapshot symlinks dereferenced and the blobs/
directory dropped — the HF cache normally stores content in blobs/ with
snapshots/ symlinking into it, which would double the bundled size when
archived naively. Keeps refs/ and .no_exist/ (the latter suppresses
offline HEAD lookups for files the hub knows don't exist).

Downloads the model first when it isn't in the local cache.
"""
import os
import shutil
import sys
from pathlib import Path

MODEL = "all-MiniLM-L6-v2"
MODEL_DIR = "models--sentence-transformers--all-MiniLM-L6-v2"
OUT = Path(__file__).parent / "build" / "hf-cache" / "hub"


def hub_cache_dir():
    for env in ("HF_HUB_CACHE",):
        if os.environ.get(env):
            return Path(os.environ[env])
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"]) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def ensure_model_cached():
    src = hub_cache_dir() / MODEL_DIR
    if src.is_dir() and any((src / "snapshots").glob("*/config.json")):
        return src
    print(f"model not in cache; downloading {MODEL}…")
    from sentence_transformers import SentenceTransformer
    SentenceTransformer(MODEL)
    if not src.is_dir():
        raise SystemExit(f"download did not populate expected cache dir {src}")
    return src


def copy_dereferenced(src: Path, dst: Path):
    """Copy the model cache dir with symlinks resolved and blobs/ omitted."""
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for entry in src.iterdir():
        if entry.name == "blobs":
            continue
        # snapshots/<rev>/* are symlinks into blobs/ — dereference them.
        shutil.copytree(entry, dst / entry.name, symlinks=False,
                        dirs_exist_ok=True) if entry.is_dir() else shutil.copy2(entry, dst / entry.name)


def main():
    src = ensure_model_cached()
    out_model = OUT / MODEL_DIR
    copy_dereferenced(src, out_model)
    # Sanity: a dereferenced snapshot must contain real files, not links.
    snapshots = list((out_model / "snapshots").glob("*/config.json"))
    if not snapshots:
        raise SystemExit("prepared cache has no snapshot config.json — copy failed")
    for cfg in snapshots:
        if cfg.is_symlink():
            raise SystemExit(f"{cfg} is still a symlink — dereference failed")
    size_mb = sum(f.stat().st_size for f in out_model.rglob("*") if f.is_file()) / 1e6
    print(f"prepared {out_model} ({size_mb:.0f} MB)")


if __name__ == "__main__":
    sys.exit(main())
