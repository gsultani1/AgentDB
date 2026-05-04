# Optional Dependency Extras

swadb has two heavyweight features behind opt-in extras. The base
package is small and works on every platform; the extras add native
binaries and native-library bindings that may not build cleanly
everywhere.

## `[ann]` — HNSW approximate nearest neighbor

```bash
pip install swadb[ann]
```

Adds **`hnswlib >= 0.8.0`**. Without it, semantic search uses
brute-force cosine similarity (correct, just O(n) per query). With it,
swadb auto-builds and maintains one HNSW index per embedding-bearing
table (`short_term_memory`, `midterm_memory`, `long_term_memory`,
`entities`, `goals`, `skills`) in a sidecar directory next to the
`.db` file.

**When to install**:
- Your DB will hold more than ~10,000 memories
- You want sub-millisecond semantic search

**When to skip**:
- You're under a few thousand memories — brute force is fine
- You're on a platform where hnswlib doesn't have wheels

The index files live at `<dbname>.ann/` (gitignored by default). They
auto-rebuild after each consolidation cycle and cover the freshness
window via a hybrid mode (ANN results from the index + brute-force
over rows added since `last_built_at`).

Manual index management:
```bash
swadb ann status         # per-table count + last_built_at
swadb ann rebuild        # rebuild all indexes
```

## `[encryption]` — SQLCipher at-rest encryption

```bash
pip install swadb[encryption]
```

Adds **`sqlcipher3 >= 0.5.0`**. Without it, the database is plain
SQLite — anyone with read access to the `.db` file can read every
memory.

With it, you can encrypt the database via the Settings → Encryption
panel:

- **Encrypt** plaintext → encrypted, with `<dbname>.preencrypt.bak`
  recovery file. Running session continues seamlessly via in-memory
  passphrase store.
- **Rekey** changes the passphrase without temporarily decrypting.
- **Disable** encrypted → plaintext, with `<dbname>.predecrypt.bak`
  recovery file.
- **Unlock screen** appears on next process start when an encrypted
  DB is detected without a passphrase. No env var needed; the user
  types the passphrase via the web UI.

CLI fallback for terminal recovery (when locked out of the UI):

```bash
swadb encryption status
swadb encryption disable --passphrase 'YOURS'
```

**When to install**:
- The `.db` file lives anywhere outside trusted machine boundaries
  (laptop, shared filesystem, backup destinations)
- Compliance requires at-rest encryption

**When to skip**:
- Single-user, local-only setup on a trusted machine
- Your platform doesn't have a `sqlcipher3` wheel and building from
  source isn't an option

## `[all]` — both extras

```bash
pip install swadb[all]
```

Equivalent to `swadb[ann,encryption]`. Recommended for production
deployments.

## `[dev]` — for contributors

```bash
pip install swadb[dev]
```

Adds:
- `pytest >= 8.0` — test suite
- `build >= 1.0` — wheel builder
- `twine >= 5.0` — PyPI uploader

Combine with editable install: `pip install -e ".[dev]"`.

## Combining extras

```bash
pip install swadb[ann,encryption]
pip install swadb[all,dev]
```

## Detection at runtime

Both extras are detected at startup:

```bash
swadb ann status
# hnswlib installed: True
```

```bash
swadb encryption status
# sqlcipher library: sqlcipher3
```

When an extra is missing, the corresponding feature is gracefully
disabled — swadb won't crash, it'll just log a one-line warning and
fall back to the non-accelerated / non-encrypted path.
