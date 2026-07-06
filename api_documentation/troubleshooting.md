# Troubleshooting

Common failure modes and their fixes. Each entry shows what you'll
actually see, why it happens, and a copy-pasteable way out.

## `pip install swadb` fails on Python 3.9

**Symptom** — on Python 3.9, installation dies in the dependency
resolver:

```
ERROR: Could not find a version that satisfies the requirement mcp>=1.0.0 (from swadb)
ERROR: No matching distribution found for mcp>=1.0.0
```

**Cause** — swadb requires Python 3.10+. The required `mcp` dependency
has no release for Python <3.10. Versions 0.1.0 and 0.1.1 wrongly
declared 3.9 support in their metadata, so pip on 3.9 selects one of
them and then fails resolving `mcp`. 0.1.2 corrected the floor to
`>=3.10` (3.9 support never actually functioned, and 3.9 has been
end-of-life since October 2025).

**Fix** — upgrade Python. There is no workaround on 3.9.

```bash
python --version          # confirm you're on < 3.10
# install Python 3.10+ from python.org or your package manager, then:
pip install swadb
```

## Port 8420 already in use when running `swadb serve`

**Symptom** — `swadb serve` exits with a raw traceback (there's no
friendly message for this yet) ending in:

```
OSError: [Errno 98] Address already in use
```

On Windows the last line reads:

```
OSError: [WinError 10048] Only one usage of each socket address (protocol/network address/port) is normally permitted
```

**Cause** — something is already bound to 8420, most often a previous
`swadb serve` that's still running.

**Fix** — either stop the other process or pick a different port:

```bash
swadb serve --port 9000
```

To find what's holding 8420: `lsof -i :8420` (macOS/Linux) or
`netstat -ano | findstr :8420` (Windows).

The companion MCP SSE port (default 8421) is configured separately —
it comes from `meta_config`, not a `serve` flag:

```bash
swadb config set mcp_port 8422    # takes effect on next serve
```

## Embedding model download stuck / slow on first run

**Symptom** — the first command that generates an embedding
(`swadb memory add`, `swadb serve`, `swadb memory search`) hangs for a
while with no output, or crawls on a slow connection.

**Cause** — sentence-transformers lazily downloads the default model
`all-MiniLM-L6-v2` (~80 MB) from Hugging Face on first use and caches
it in `~/.cache/huggingface` (`%USERPROFILE%\.cache\huggingface` on
Windows). Nothing is stuck; it's just downloading with no progress
output.

**Fix** — pre-warm the cache once, deliberately, so first real use is
instant:

```bash
python -c "from swadb.embeddings import get_model; get_model()"
```

For air-gapped or firewalled machines: run the pre-warm on a networked
machine, then copy the model's cache directory
(`~/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2`)
to the same path on the target. The underlying Hugging Face libraries
honor `HF_HOME` (relocate the cache) and `HF_HUB_OFFLINE=1` (never hit
the network); swadb itself has no offline flag or preseed command —
those knobs belong to sentence-transformers/huggingface_hub.

To skip embedding generation entirely for a single insert:

```bash
swadb memory add "content" --no-embedding
```

## `sqlcipher3` will not install (`swadb[encryption]`)

**Symptom** — `pip install swadb[encryption]` fails building a wheel,
typically with a missing-compiler or missing-SQLCipher-headers error.
Windows is the usual offender.

**Cause** — `sqlcipher3` has limited prebuilt wheels; on platforms
without one, pip builds from source, which needs a C toolchain plus the
SQLCipher library and headers.

**Fix** — try the prebuilt-wheel distribution of the same project:

```bash
pip install sqlcipher3-binary
```

It installs the same `sqlcipher3` module, and swadb detects either
`sqlcipher3` or `pysqlcipher3` at import time — you just can't get it
via the `[encryption]` extra (which pins the source distribution).
Wheel coverage varies by platform and Python version; check PyPI for
yours.

If neither installs, you can simply go without: encryption is the only
feature that's lost, the rest of swadb runs fine on plain SQLite.
Confirm the state with:

```bash
swadb encryption status
# sqlcipher library: NOT INSTALLED
```

## Encrypted DB lockout / wrong passphrase

**Symptom** — one of:

- `swadb serve` prints a `DATABASE IS LOCKED` banner and every API call
  except health/unlock returns `423 Locked`; the web UI shows an unlock
  screen.
- A CLI command fails with
  `RuntimeError: Database at swadb.db is encrypted but no passphrase was provided.`
- With a *wrong* passphrase set, the first query fails with
  `sqlite3.DatabaseError: file is not a database` (SQLCipher can't tell
  "wrong key" from "not a database" — that error *is* the wrong-key
  error).

**Cause** — the `.db` file on disk is SQLCipher-encrypted and the
process either has no passphrase or the wrong one. The passphrase is
read from, in priority order: the in-memory store (set via the UI
unlock screen), `SWADB_PASSPHRASE`, then `AGENTDB_PASSPHRASE`
(deprecated, prints a one-shot rename warning).

**Fix** — if you know the passphrase, either type it into the UI unlock
screen (no restart needed) or set the env var and restart:

```bash
export SWADB_PASSPHRASE='YOURS'     # PowerShell: $env:SWADB_PASSPHRASE = 'YOURS'
swadb serve
```

If the UI has locked you out entirely, recover from the terminal:

```bash
swadb encryption status
swadb encryption disable --passphrase 'YOURS'
```

If you've **lost the passphrase**: check for
`swadb.db.preencrypt.bak` next to the database — it's the plaintext
copy saved at the moment of original encryption, and restoring it
recovers everything up to that point (`swadb encryption status` lists
it if present). Without the passphrase and without that backup, the
data is unrecoverable. That's the point of at-rest encryption — there
is no reset flow and no backdoor.

## `swadb` command not found after `pip install`

**Symptom** — `command not found: swadb` (macOS/Linux) or
`'swadb' is not recognized as an internal or external command` (Windows),
usually after pip warned during install:

```
WARNING: The script swadb.exe is installed in '...' which is not on PATH.
```

**Cause** — the `swadb` console script lands in Python's scripts
directory, which isn't always on PATH — most commonly with `--user`
installs and Windows Store Python, where the Scripts dir is buried
under the user profile.

**Fix** — the module form always works, no PATH required (0.1.1+;
on 0.1.0 use `python -m swadb.cli`):

```bash
python -m swadb --help
```

Or add the scripts directory to PATH. Find it with:

```bash
python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
```

## `hnswlib` install fails or crashes (`swadb[ann]`)

**Symptom** — two distinct failures:

1. **Install-time**: `pip install swadb[ann]` fails compiling, e.g.
   `error: Microsoft Visual C++ 14.0 or greater is required` on Windows
   or a missing `g++` on Linux.
2. **Run-time**: Python dies instantly with an illegal-instruction
   fault (SIGILL, exit code 132) when swadb touches the ANN index.

**Cause** — hnswlib ships source-only, so pip must compile it: no C++
toolchain means failure (1). By default it compiles with
`-march=native`, so a wheel built on one CPU (a shared pip cache, a CI
runner, a copied venv) can crash on another (2).

**Fix** — install a C++ toolchain (VS Build Tools on Windows,
`g++`/`clang` elsewhere), then build portably and bypass any poisoned
cache:

```bash
HNSWLIB_NO_NATIVE=1 pip install --no-cache-dir hnswlib
```

PowerShell equivalent:

```powershell
$env:HNSWLIB_NO_NATIVE = '1'; pip install --no-cache-dir hnswlib
```

Verify with:

```bash
swadb ann status
# hnswlib installed: True
```

Or skip it entirely — without hnswlib, semantic search falls back to
brute-force cosine similarity (correct, just O(n) per query), which is
fine below a few thousand memories.
