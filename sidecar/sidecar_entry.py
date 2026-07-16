"""
Frozen entry point for the swadb sidecar binary.

Environment setup MUST happen before any swadb / huggingface import: the
bundled embedding-model cache is wired up via HF_HUB_CACHE so the sidecar
is fully offline out of the box. When the bundle carries no cache (built
without prepare_hf_cache.py), the normal online resolution applies.
"""
import os
import sys


def _bundle_root():
    # onedir layout: sys._MEIPASS == <dist>/swadb-sidecar/_internal
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))


_hf_cache = os.path.join(_bundle_root(), "hf-cache", "hub")
if os.path.isdir(_hf_cache):
    # setdefault: explicit user env always wins over the bundled cache.
    os.environ.setdefault("HF_HUB_CACHE", _hf_cache)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

from swadb.cli import main  # noqa: E402  (env setup must precede this import)

if __name__ == "__main__":
    sys.exit(main())
