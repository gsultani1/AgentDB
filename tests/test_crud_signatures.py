"""
Catch the "broken handler shape" bug class systematically.

Every CRUD function we've shipped a UI for in this round was previously
called by the HTTP handler with the wrong shape. None of those calls
crashed in production because the UI never drove them — they sat broken.

These tests call each CRUD function with its documented signature so
ANY signature drift between CRUD and handler shows up as a fast,
local pytest failure instead of a 500 in the browser six months later.

If you're adding a new CRUD function with a non-trivial argument shape:
add a corresponding test here so the next refactor catches an
accidental misuse.
"""
import pytest

from swadb import crud


class TestMemoryCRUD:
    def test_short_term_create_and_round_trip(self, fresh_db):
        mid = crud.create_short_term_memory(fresh_db, "hello", "conversation")
        row = crud.get_short_term_memory(fresh_db, mid)
        assert row is not None
        assert row["content"] == "hello"

    def test_short_term_update_signature(self, fresh_db):
        mid = crud.create_short_term_memory(fresh_db, "x", "conversation")
        ok = crud.update_short_term_memory(fresh_db, mid, content="updated")
        assert ok is True
        row = crud.get_short_term_memory(fresh_db, mid)
        assert row["content"] == "updated"

    def test_midterm_round_trip(self, fresh_db):
        mid = crud.create_midterm_memory(
            fresh_db, "mid memory", confidence=0.5, entity_ids=["e1"],
        )
        row = crud.get_midterm_memory(fresh_db, mid)
        assert row is not None
        # entity_ids is a JSON column; round-trip preserves the list
        import json
        assert json.loads(row["entity_ids"]) == ["e1"]


class TestBatchMemorySignatures:
    """The shapes the HTTP handler reshapes its body into. These caught
    the original bug — see commit b6426bf."""

    def _seed(self, conn, n=3):
        return [
            crud.create_short_term_memory(conn, f"m{i}", "conversation")
            for i in range(n)
        ]

    def test_batch_pin_takes_id_table_pairs(self, fresh_db):
        ids = self._seed(fresh_db, 2)
        pairs = [(i, "short_term_memory") for i in ids]
        result = crud.batch_pin_memories(fresh_db, pairs, agent_id="default")
        assert isinstance(result, list)
        assert len(result) == 2
        # Verify pin rows actually written
        n = fresh_db.execute("SELECT COUNT(*) FROM pinned_memories").fetchone()[0]
        assert n == 2

    def test_batch_tag_takes_pairs_and_tag_id(self, fresh_db):
        ids = self._seed(fresh_db, 3)
        tag_id = crud.create_tag(fresh_db, "important")
        pairs = [(i, "short_term_memory") for i in ids]
        crud.batch_tag_memories(fresh_db, pairs, tag_id)
        n = fresh_db.execute(
            "SELECT COUNT(*) FROM tag_assignments WHERE tag_id = ?", (tag_id,)
        ).fetchone()[0]
        assert n == 3

    def test_batch_delete_pairs_soft_deletes_stm(self, fresh_db):
        ids = self._seed(fresh_db, 2)
        pairs = [(i, "short_term_memory") for i in ids]
        crud.batch_delete_memories(fresh_db, pairs)
        n = fresh_db.execute(
            "SELECT COUNT(*) FROM short_term_memory WHERE status = 'expired'"
        ).fetchone()[0]
        assert n == 2

    def test_batch_promote_takes_ids_and_tier_string(self, fresh_db):
        ids = self._seed(fresh_db, 2)
        # Note: takes flat list of IDs + a "from_tier" string, NOT pairs
        promoted = crud.batch_promote_memories(fresh_db, ids, "short")
        assert len(promoted) == 2
        n = fresh_db.execute("SELECT COUNT(*) FROM midterm_memory").fetchone()[0]
        assert n == 2


class TestFileAccessGrants:
    """The grants endpoint had a positional-arg signature mismatch. The
    keyword-arg form below is what the fixed handler uses."""

    def test_create_grant_with_keyword_args(self, fresh_db, tmp_path):
        d = str(tmp_path)
        gid = crud.create_file_access_grant(
            fresh_db,
            directory_path=d,
            agent_id="default",
            permission="read",
        )
        assert gid
        grants = crud.list_file_access_grants(fresh_db, agent_id="default")
        assert len(grants) == 1
        assert grants[0]["directory_path"] == d


class TestQueryCacheCRUD:
    def test_hash_is_stable_for_equivalent_queries(self):
        h1 = crud.query_cache_hash("Hello World", "default", {})
        h2 = crud.query_cache_hash("  hello   world ", "default", {})
        assert h1 == h2  # whitespace + case normalized

    def test_hash_differs_by_filter(self):
        h1 = crud.query_cache_hash("q", "default", {})
        h2 = crud.query_cache_hash("q", "default", {"tier": "long"})
        assert h1 != h2

    def test_insert_and_lookup(self, fresh_db):
        h = crud.query_cache_hash("the question", "default", {})
        crud.insert_query_cache_entry(
            fresh_db, h, "the question", "default",
            {"memories": {"short_term": []}}, ["mem1", "mem2"],
        )
        result = crud.get_cached_query_result(fresh_db, h, ttl_hours=24)
        assert result is not None
        assert "memories" in result

    def test_invalidate_drops_referencing_rows(self, fresh_db):
        h = crud.query_cache_hash("q", "default", {})
        crud.insert_query_cache_entry(
            fresh_db, h, "q", "default", {"x": 1}, ["mem-target", "other"],
        )
        crud.invalidate_query_cache_for_memory(fresh_db, "mem-target")
        n = fresh_db.execute("SELECT COUNT(*) FROM query_cache").fetchone()[0]
        assert n == 0  # row referenced our memory_id, gone


class TestProviderResolution:
    def test_get_llm_config_empty_when_no_providers(self, fresh_db):
        from swadb.middleware import get_llm_config
        cfg = get_llm_config(fresh_db)
        assert cfg == {}

    def test_default_provider_resolves(self, fresh_db):
        from swadb.middleware import get_llm_config
        crud.create_llm_provider(
            fresh_db, name="My Claude", provider_type="claude",
            model="claude-sonnet-4-6", api_key="sk-test", is_default=True,
        )
        cfg = get_llm_config(fresh_db)
        assert cfg["llm_provider"] == "claude"
        assert cfg["llm_model"] == "claude-sonnet-4-6"
        assert cfg["llm_api_key"] == "sk-test"

    def test_flat_keys_not_seeded_in_new_db(self, fresh_db):
        flat = ["llm_provider", "llm_api_key", "llm_model", "llm_endpoint"]
        rows = fresh_db.execute(
            f"SELECT key FROM meta_config WHERE key IN ({','.join('?' * len(flat))})",
            flat,
        ).fetchall()
        assert len(rows) == 0


class TestAdapterRegistry:
    """All 6 PRD-spec adapter types must be in middleware.ADAPTERS, plus
    the local + custom helpers, with the contract method present."""

    def test_all_seven_adapters_registered(self):
        from swadb.middleware import ADAPTERS
        expected = {"claude", "openai", "local", "ollama",
                    "llamacpp", "lmstudio", "custom"}
        assert set(ADAPTERS.keys()) == expected

    def test_each_adapter_implements_call_provider(self):
        from swadb.middleware import ADAPTERS, get_adapter
        for name in ADAPTERS:
            inst = get_adapter(name)
            assert hasattr(inst, "call_provider"), \
                f"{name} adapter missing call_provider method"

    def test_unknown_provider_falls_back_to_custom(self):
        from swadb.middleware import get_adapter, CustomAdapter
        inst = get_adapter("definitely-not-a-real-provider-type")
        assert isinstance(inst, CustomAdapter)
