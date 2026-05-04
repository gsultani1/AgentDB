"""
Query cache: lookup, sleep-time pre-compute, and invalidation on memory writes.
"""
import json
import pytest

from swadb import crud
from swadb.embeddings import embedding_to_blob
import numpy as np


def _seed_with_synthetic_embeddings(conn, contents, seed=42):
    """Seed STM rows with random unit-normalized vectors, no LLM required."""
    rng = np.random.default_rng(seed)
    for content in contents:
        v = rng.normal(size=384).astype(np.float32)
        v /= np.linalg.norm(v) + 1e-9
        crud.create_short_term_memory(
            conn, content=content, source="conversation",
            embedding=embedding_to_blob(v),
        )


class TestCacheLookupAndInvalidation:
    def test_get_returns_none_on_miss(self, fresh_db):
        h = crud.query_cache_hash("never-seen", "default", {})
        assert crud.get_cached_query_result(fresh_db, h) is None

    def test_insert_then_lookup_round_trip(self, fresh_db):
        h = crud.query_cache_hash("the question", "default", {})
        crud.insert_query_cache_entry(
            fresh_db, h, "the question", "default",
            {"memories": {"short_term": [{"id": "m1"}]}}, ["m1"],
        )
        result = crud.get_cached_query_result(fresh_db, h)
        assert result is not None
        assert result["memories"]["short_term"][0]["id"] == "m1"

    def test_ttl_expiry(self, fresh_db):
        h = crud.query_cache_hash("q", "default", {})
        crud.insert_query_cache_entry(fresh_db, h, "q", "default", {}, [])
        # Backdate the row by 48h, ttl is 24h → miss
        fresh_db.execute(
            "UPDATE query_cache SET computed_at = datetime('now', '-48 hours') "
            "WHERE query_hash = ?", (h,),
        )
        fresh_db.commit()
        assert crud.get_cached_query_result(fresh_db, h, ttl_hours=24) is None

    def test_insert_replaces_prior_entry_with_same_hash(self, fresh_db):
        h = crud.query_cache_hash("q", "default", {})
        crud.insert_query_cache_entry(fresh_db, h, "q", "default", {"v": 1}, [])
        crud.insert_query_cache_entry(fresh_db, h, "q", "default", {"v": 2}, [])
        rows = fresh_db.execute(
            "SELECT COUNT(*) FROM query_cache WHERE query_hash = ?", (h,)
        ).fetchone()[0]
        assert rows == 1
        result = crud.get_cached_query_result(fresh_db, h)
        assert result["v"] == 2

    def test_invalidate_drops_only_referencing_rows(self, fresh_db):
        h1 = crud.query_cache_hash("q1", "default", {})
        h2 = crud.query_cache_hash("q2", "default", {})
        crud.insert_query_cache_entry(fresh_db, h1, "q1", "default", {}, ["m-target", "other"])
        crud.insert_query_cache_entry(fresh_db, h2, "q2", "default", {}, ["only-other"])
        crud.invalidate_query_cache_for_memory(fresh_db, "m-target")
        # h1 referenced m-target → gone. h2 unaffected.
        assert crud.get_cached_query_result(fresh_db, h1) is None
        assert crud.get_cached_query_result(fresh_db, h2) is not None


class TestUpdateInvalidatesCache:
    def test_update_short_term_invalidates(self, fresh_db):
        mid = crud.create_short_term_memory(fresh_db, "x", "conversation")
        h = crud.query_cache_hash("q", "default", {})
        crud.insert_query_cache_entry(fresh_db, h, "q", "default", {}, [mid])
        crud.update_short_term_memory(fresh_db, mid, content="updated")
        assert crud.get_cached_query_result(fresh_db, h) is None

    def test_delete_short_term_invalidates(self, fresh_db):
        mid = crud.create_short_term_memory(fresh_db, "x", "conversation")
        h = crud.query_cache_hash("q", "default", {})
        crud.insert_query_cache_entry(fresh_db, h, "q", "default", {}, [mid])
        crud.delete_short_term_memory(fresh_db, mid)
        assert crud.get_cached_query_result(fresh_db, h) is None


class TestSleepPreCompute:
    """Phase 1c of run_sleep_cycle picks frequent context_snapshots and
    pre-computes them. Marked slow because it loads the embedding model."""

    @pytest.mark.slow
    def test_pre_compute_writes_cache_for_frequent_query(self, fresh_db):
        # Need a real embedding to drive retrieve_context, so use the model
        from swadb.embeddings import generate_embedding
        from swadb.context import retrieve_context
        from swadb.sleep import _pre_compute_query_cache, _load_sleep_config

        for content in ["alice met bob", "bob met charlie"]:
            emb = generate_embedding(content)
            crud.create_short_term_memory(
                fresh_db, content=content, source="conversation",
                embedding=embedding_to_blob(emb),
            )

        # Drive a snapshot via retrieve_context — populates context_snapshots
        QUERY = "who did alice meet"
        retrieve_context(fresh_db, QUERY, agent_id="default")

        config = _load_sleep_config(fresh_db)
        config.setdefault("sleep_pre_compute_enabled", "true")
        config.setdefault("sleep_pre_compute_top_n", "10")
        config.setdefault("cache_ttl_hours", "24")
        result = _pre_compute_query_cache(fresh_db, config)

        # The pre-computer picked up our 1 unique query
        assert result.get("warmed", 0) >= 1
        cache_rows = fresh_db.execute("SELECT COUNT(*) FROM query_cache").fetchone()[0]
        assert cache_rows >= 1
