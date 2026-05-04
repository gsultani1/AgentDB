"""
ANN index — correctness, hybrid mode for fresh inserts, persistence.
"""
import numpy as np
import pytest

from swadb import crud
from swadb.embeddings import embedding_to_blob, semantic_search
from swadb import ann


def _seed_synthetic(conn, n, seed=42):
    rng = np.random.default_rng(seed)
    for i in range(n):
        v = rng.normal(size=384).astype(np.float32)
        v /= np.linalg.norm(v) + 1e-9
        crud.create_short_term_memory(
            conn, content=f"synth {i}", source="conversation",
            embedding=embedding_to_blob(v),
        )


def _random_query(seed):
    rng = np.random.default_rng(seed)
    v = rng.normal(size=384).astype(np.float32)
    v /= np.linalg.norm(v) + 1e-9
    return v


@pytest.fixture
def reset_ann_singleton():
    """ANN module has process-level state; clear between tests."""
    ann.reset_index_set()
    yield
    ann.reset_index_set()


@pytest.mark.skipif(not ann.is_available(), reason="hnswlib not installed")
class TestAnnIndex:
    def test_build_and_count(self, fresh_db, tmp_db_path, reset_ann_singleton):
        _seed_synthetic(fresh_db, 200)
        idx_set = ann.get_index_set(tmp_db_path)
        idx_set.load_or_build(fresh_db)
        stm = idx_set.for_table("short_term_memory")
        assert stm.count() == 200

    def test_recall_within_threshold(self, fresh_db, tmp_db_path, reset_ann_singleton):
        """Uniform-random unit vectors are HNSW's worst-case data
        distribution. Production embeddings cluster heavily and hit 0.95+."""
        _seed_synthetic(fresh_db, 500)
        idx_set = ann.get_index_set(tmp_db_path)
        idx_set.load_or_build(fresh_db)

        rows = fresh_db.execute(
            "SELECT id, embedding FROM short_term_memory WHERE embedding IS NOT NULL"
        ).fetchall()
        candidates = [(r["id"], r["embedding"]) for r in rows]

        K = 10
        recalls = []
        for q in range(10):
            query = _random_query(seed=q + 1000)
            ann_hits = idx_set.search(fresh_db, "short_term_memory", query, top_k=K)
            brute = semantic_search(query, candidates, top_k=K)
            ann_ids = {h[0] for h in ann_hits}
            brute_ids = {h[0] for h in brute}
            if brute_ids:
                recalls.append(len(ann_ids & brute_ids) / len(brute_ids))
        avg = sum(recalls) / len(recalls) if recalls else 0
        # 0.7 floor for uniform-random worst-case
        assert avg >= 0.70, f"recall {avg:.3f} below 0.70"

    def test_hybrid_mode_finds_post_build_inserts(self, fresh_db, tmp_db_path, reset_ann_singleton):
        """Memories inserted AFTER index build must still be findable via
        the freshness brute-force tail. Without hybrid mode, this is the
        bug that turns ANN into a regression."""
        _seed_synthetic(fresh_db, 50)
        idx_set = ann.get_index_set(tmp_db_path)
        idx_set.load_or_build(fresh_db)

        # Insert a fresh memory after the build
        fresh_v = _random_query(seed=99999)
        fresh_id = crud.create_short_term_memory(
            fresh_db, content="needle in haystack", source="conversation",
            embedding=embedding_to_blob(fresh_v),
        )
        # Search with the fresh vector itself; it should appear in the result
        hits = idx_set.search(fresh_db, "short_term_memory", fresh_v, top_k=5)
        ids = [h[0] for h in hits]
        assert fresh_id in ids, \
            f"fresh row {fresh_id} not in ANN hybrid results {ids}"

    def test_save_and_reload(self, fresh_db, tmp_db_path, reset_ann_singleton):
        _seed_synthetic(fresh_db, 50)
        idx_set = ann.get_index_set(tmp_db_path)
        idx_set.load_or_build(fresh_db)

        # Drop the in-memory state and load from disk
        ann.reset_index_set()
        idx_set2 = ann.get_index_set(tmp_db_path)
        summary = idx_set2.load_or_build(fresh_db)
        assert summary["loaded"] >= 1  # loaded from disk, didn't rebuild
