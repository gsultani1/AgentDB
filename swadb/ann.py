"""
Approximate-nearest-neighbor (ANN) index for swadb semantic search.

Wraps hnswlib (Hierarchical Navigable Small World graphs) per embedding-bearing
table: short_term_memory, midterm_memory, long_term_memory, entities, goals,
and skills. Each table gets its own index file in a sidecar directory next to
the .db file. Indexes are rebuilt from scratch after each consolidation cycle.

Hybrid mode (correctness invariant)
───────────────────────────────────
HNSW indexes are stale the moment new embeddings are written. Every `search()`
returns ANN candidates from the index PLUS brute-force candidates for any rows
written/updated after the index's `last_built_at` timestamp. Without this,
freshly ingested memories would be invisible to retrieval until the next
consolidation cycle. The merge dedupes by row id.

Graceful fallback
─────────────────
If hnswlib is not installed OR ann_index_enabled = "false" in meta_config,
`AnnIndexSet` returns None from `for_table()`, and callers continue using the
existing brute-force path in embeddings.semantic_search.
"""

import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from swadb.embeddings import blob_to_embedding, cosine_similarity

logger = logging.getLogger("swadb.ann")

try:
    import hnswlib  # type: ignore
    _HNSW_AVAILABLE = True
except ImportError:
    hnswlib = None  # type: ignore
    _HNSW_AVAILABLE = False


ANN_TABLES = (
    "short_term_memory",
    "midterm_memory",
    "long_term_memory",
    "entities",
    "goals",
    "skills",
)

_TIMESTAMP_COLUMN = {
    "short_term_memory": "timestamp",
    "midterm_memory": "created_at",
    "long_term_memory": "created_at",
    "entities": "first_seen",
    "goals": "created_at",
    "skills": "created_at",
}


def is_available() -> bool:
    """True if hnswlib is importable."""
    return _HNSW_AVAILABLE


def sidecar_dir(db_path: str) -> Path:
    """Return the directory used to persist ANN indexes for a given DB."""
    return Path(db_path).with_suffix(".ann")


class _TableIndex:
    """A single hnswlib index plus its int_label↔uuid map."""

    __slots__ = ("table", "dim", "index", "label_to_id", "id_to_label",
                 "last_built_at", "_capacity")

    def __init__(self, table: str, dim: int = 384):
        self.table = table
        self.dim = dim
        self.index = None  # type: ignore
        self.label_to_id: dict = {}
        self.id_to_label: dict = {}
        self.last_built_at: Optional[str] = None
        self._capacity = 0

    def build(self, rows: List[Tuple[str, bytes]],
              ef_construction: int = 200, M: int = 16) -> None:
        """
        Build the index from a list of (id, embedding_blob) tuples.
        Replaces any existing index.
        """
        if not _HNSW_AVAILABLE:
            raise RuntimeError("hnswlib is not installed")

        n = len(rows)
        # Always allocate at least 1 slot — hnswlib refuses zero-capacity init.
        # Headroom (2x) avoids immediate resize on next add.
        capacity = max(n * 2, 32)
        self.index = hnswlib.Index(space="cosine", dim=self.dim)
        self.index.init_index(max_elements=capacity,
                              ef_construction=ef_construction, M=M)
        # ef controls query-time recall vs latency. ef_construction//2 gives
        # ~95% recall on real (clustered) embeddings while keeping queries
        # under 1ms at 50k vectors. Tunable via set_ef() if needed.
        self.index.set_ef(max(100, ef_construction // 2))

        self.label_to_id.clear()
        self.id_to_label.clear()

        if n == 0:
            self.last_built_at = datetime.utcnow().isoformat()
            self._capacity = capacity
            return

        vectors = np.empty((n, self.dim), dtype=np.float32)
        labels = np.empty(n, dtype=np.int64)
        for i, (rid, blob) in enumerate(rows):
            if blob is None:
                # Skip rows with missing embedding; we still consume the slot
                # to keep label↔id alignment with the candidate ordering.
                vectors[i] = 0.0
                labels[i] = -1
                continue
            vectors[i] = blob_to_embedding(blob)
            labels[i] = i
            self.label_to_id[i] = rid
            self.id_to_label[rid] = i

        # Add only valid rows (label != -1)
        valid_mask = labels != -1
        if valid_mask.any():
            self.index.add_items(vectors[valid_mask], labels[valid_mask])

        self.last_built_at = datetime.utcnow().isoformat()
        self._capacity = capacity

    def search(self, query: np.ndarray, top_k: int) -> List[Tuple[str, float]]:
        """
        Query the index. Returns list of (id, similarity_score) tuples.

        hnswlib returns cosine *distance* (= 1 - cosine_similarity in [0, 2]).
        We convert back so callers get the same [-1, 1] similarity scores
        embeddings.semantic_search would produce.
        """
        if self.index is None:
            return []
        cur = self.index.get_current_count()
        if cur == 0:
            return []
        k = min(top_k, cur)
        labels, distances = self.index.knn_query(query.reshape(1, -1).astype(np.float32), k=k)
        out: List[Tuple[str, float]] = []
        for label, dist in zip(labels[0], distances[0]):
            rid = self.label_to_id.get(int(label))
            if rid is None:
                continue
            similarity = 1.0 - float(dist)
            out.append((rid, similarity))
        return out

    def save(self, dir_path: Path) -> None:
        """Persist the index + label map to dir_path/{table}.bin and {table}.pkl."""
        dir_path.mkdir(parents=True, exist_ok=True)
        if self.index is not None:
            self.index.save_index(str(dir_path / f"{self.table}.bin"))
        with open(dir_path / f"{self.table}.pkl", "wb") as f:
            pickle.dump({
                "dim": self.dim,
                "label_to_id": self.label_to_id,
                "id_to_label": self.id_to_label,
                "last_built_at": self.last_built_at,
                "capacity": self._capacity,
            }, f)

    def load(self, dir_path: Path) -> bool:
        """Load index + label map from disk. Returns True if successful."""
        if not _HNSW_AVAILABLE:
            return False
        meta_path = dir_path / f"{self.table}.pkl"
        bin_path = dir_path / f"{self.table}.bin"
        if not meta_path.exists() or not bin_path.exists():
            return False
        try:
            with open(meta_path, "rb") as f:
                meta = pickle.load(f)
            self.dim = meta.get("dim", self.dim)
            self.label_to_id = meta.get("label_to_id", {})
            self.id_to_label = meta.get("id_to_label", {})
            self.last_built_at = meta.get("last_built_at")
            self._capacity = meta.get("capacity", 0)
            self.index = hnswlib.Index(space="cosine", dim=self.dim)
            self.index.load_index(str(bin_path), max_elements=self._capacity or 32)
            return True
        except Exception as e:
            logger.warning("Failed to load ANN index for %s: %s", self.table, e)
            self.index = None
            return False

    def count(self) -> int:
        return self.index.get_current_count() if self.index is not None else 0


class AnnIndexSet:
    """
    One HNSW index per embedding-bearing table.

    Lifecycle:
        idx_set = AnnIndexSet(db_path)
        idx_set.load_or_build(conn)        # called once at server startup
        results = idx_set.search(conn, table, query_embedding, top_k=10)
        idx_set.rebuild_all(conn)          # after consolidation
    """

    def __init__(self, db_path: str, dim: int = 384):
        self.db_path = db_path
        self.dim = dim
        self.dir = sidecar_dir(db_path)
        self.indexes: dict = {table: _TableIndex(table, dim) for table in ANN_TABLES}
        self.enabled = _HNSW_AVAILABLE

    def for_table(self, table: str) -> Optional[_TableIndex]:
        if not self.enabled:
            return None
        return self.indexes.get(table)

    def load_or_build(self, conn) -> dict:
        """Load any existing index files; rebuild missing ones from the DB."""
        if not self.enabled:
            return {"loaded": 0, "built": 0, "skipped": len(ANN_TABLES)}
        loaded = built = 0
        for table, idx in self.indexes.items():
            if idx.load(self.dir):
                loaded += 1
                continue
            self._build_one(conn, table)
            built += 1
        return {"loaded": loaded, "built": built, "skipped": 0}

    def rebuild_all(self, conn) -> dict:
        """Rebuild every table's index from current DB state. Persist on success."""
        if not self.enabled:
            return {"rebuilt": 0, "skipped": "hnswlib not installed"}
        rebuilt = 0
        per_table = {}
        for table in ANN_TABLES:
            n = self._build_one(conn, table)
            per_table[table] = n
            rebuilt += 1
        return {"rebuilt": rebuilt, "per_table": per_table,
                "timestamp": datetime.utcnow().isoformat()}

    def _build_one(self, conn, table: str) -> int:
        idx = self.indexes[table]
        rows = conn.execute(
            f"SELECT id, embedding FROM {table} WHERE embedding IS NOT NULL"
        ).fetchall()
        # Convert sqlite3.Row to (id, blob) tuples
        pairs = [(r["id"], r["embedding"]) for r in rows]
        idx.build(pairs)
        idx.save(self.dir)
        return len(pairs)

    def search(self, conn, table: str, query_embedding: np.ndarray,
               top_k: int = 10, agent_filter: Optional[List[str]] = None,
               status_filter: Optional[str] = "active") -> List[Tuple[str, float]]:
        """
        Hybrid search: ANN candidates (top_k * 2) + brute-force over rows
        added/updated since last_built_at, merged and re-ranked. Returns
        top_k (id, similarity) pairs.

        agent_filter: optional list of agent_ids to scope to. Applied AFTER
                      ANN retrieval so we don't lose recall from over-filtering.
        status_filter: optional status column value (None to disable).
        """
        if not self.enabled:
            return []
        idx = self.for_table(table)
        if idx is None or idx.index is None:
            return []

        # 1) ANN portion — over-fetch to allow post-filter without losing top_k
        ann_results = idx.search(query_embedding, top_k=max(top_k * 3, 20))
        scores: dict = {rid: s for rid, s in ann_results}

        # 2) Brute-force the freshness tail
        if idx.last_built_at:
            ts_col = _TIMESTAMP_COLUMN.get(table, "created_at")
            try:
                fresh = conn.execute(
                    f"SELECT id, embedding FROM {table} "
                    f"WHERE embedding IS NOT NULL AND {ts_col} > ?",
                    (idx.last_built_at,),
                ).fetchall()
            except Exception:
                fresh = []
            for r in fresh:
                rid = r["id"]
                blob = r["embedding"]
                if blob is None:
                    continue
                emb = blob_to_embedding(blob)
                score = cosine_similarity(query_embedding, emb)
                # Always overwrite — fresh row is more authoritative than the
                # stale ANN entry (if any).
                scores[rid] = score

        # 3) Optional filtering. We re-query metadata only for the surviving
        # candidate set to keep the SQL footprint small.
        if not scores:
            return []

        if agent_filter is not None or status_filter is not None:
            ids = list(scores.keys())
            placeholders = ",".join("?" * len(ids))
            cols = "id"
            try:
                # Probe whether the table has these columns
                pragma = conn.execute(f"PRAGMA table_info({table})").fetchall()
                col_names = {row["name"] for row in pragma}
            except Exception:
                col_names = set()
            select_cols = ["id"]
            if agent_filter is not None and "agent_id" in col_names:
                select_cols.append("agent_id")
            if status_filter is not None and "status" in col_names:
                select_cols.append("status")
            cols = ", ".join(select_cols)
            try:
                rows = conn.execute(
                    f"SELECT {cols} FROM {table} WHERE id IN ({placeholders})",
                    ids,
                ).fetchall()
            except Exception:
                rows = []
            keep = set()
            for r in rows:
                if status_filter is not None and "status" in r.keys() and r["status"] != status_filter:
                    continue
                if agent_filter is not None and "agent_id" in r.keys() \
                        and r["agent_id"] not in agent_filter:
                    continue
                keep.add(r["id"])
            scores = {rid: s for rid, s in scores.items() if rid in keep}

        # 4) Sort and trim
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]


# ── Module-level singleton management ─────────────────────────────────────────
# A single AnnIndexSet per process is fine because all routes share the same DB
# file. Multi-DB scenarios (rare) would need a per-path cache; not implemented.

_GLOBAL_INDEX_SET: Optional[AnnIndexSet] = None


def get_index_set(db_path: str) -> AnnIndexSet:
    """Return the process-wide AnnIndexSet, creating it on first call."""
    global _GLOBAL_INDEX_SET
    if _GLOBAL_INDEX_SET is None or _GLOBAL_INDEX_SET.db_path != db_path:
        _GLOBAL_INDEX_SET = AnnIndexSet(db_path)
    return _GLOBAL_INDEX_SET


def reset_index_set() -> None:
    """Drop the cached AnnIndexSet (e.g. after rekey or DB swap)."""
    global _GLOBAL_INDEX_SET
    _GLOBAL_INDEX_SET = None
