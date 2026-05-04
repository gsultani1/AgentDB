"""
Entity detail aggregation: memories referencing an entity, relations
with resolved other-name, co-occurring entities via JSON1 CTE.
"""
import pytest
from swadb import crud


@pytest.fixture
def entity_fixture(fresh_db):
    """Three entities + four memories with overlapping entity_ids."""
    alice = crud.create_entity(fresh_db, canonical_name="alice", entity_type="person")
    bob = crud.create_entity(fresh_db, canonical_name="bob", entity_type="person")
    charlie = crud.create_entity(fresh_db, canonical_name="charlie", entity_type="person")

    m1 = crud.create_midterm_memory(fresh_db, "alice and bob met", entity_ids=[alice, bob])
    m2 = crud.create_midterm_memory(fresh_db, "alice talked to charlie", entity_ids=[alice, charlie])
    m3 = crud.create_midterm_memory(fresh_db, "bob and charlie disagreed", entity_ids=[bob, charlie])
    m4 = crud.create_midterm_memory(fresh_db, "alice prefers Python", entity_ids=[alice])

    crud.create_relation(fresh_db, alice, "entities", bob, "entities",
                         edge_type="related_to", weight=0.7)
    return {
        "conn": fresh_db,
        "alice": alice, "bob": bob, "charlie": charlie,
        "m1": m1, "m2": m2, "m3": m3, "m4": m4,
    }


def _memories_for(conn, eid, mem_limit=50):
    """Mirror _op_entity_detail's memory query."""
    out = []
    for tier_label, table in (("midterm", "midterm_memory"),
                              ("long_term", "long_term_memory")):
        rows = conn.execute(
            f"SELECT m.*, ? AS tier FROM {table} m, json_each(m.entity_ids) j "
            f"WHERE j.value = ? ORDER BY m.created_at DESC LIMIT ?",
            (tier_label, eid, mem_limit),
        ).fetchall()
        for r in rows:
            d = dict(r)
            d.pop("embedding", None)
            out.append(d)
    return out


def _co_occurring_for(conn, eid):
    """Mirror _op_entity_detail's co-occurring CTE."""
    rows = conn.execute(
        """
        WITH my_memories AS (
            SELECT m.id AS mid FROM midterm_memory m, json_each(m.entity_ids) j
            WHERE j.value = ?
            UNION
            SELECT m.id AS mid FROM long_term_memory m, json_each(m.entity_ids) j
            WHERE j.value = ?
        ),
        co_ids AS (
            SELECT j.value AS eid FROM midterm_memory m, json_each(m.entity_ids) j
            WHERE m.id IN (SELECT mid FROM my_memories) AND j.value != ?
            UNION ALL
            SELECT j.value AS eid FROM long_term_memory m, json_each(m.entity_ids) j
            WHERE m.id IN (SELECT mid FROM my_memories) AND j.value != ?
        )
        SELECT eid, COUNT(*) AS freq FROM co_ids
        GROUP BY eid ORDER BY freq DESC LIMIT 20
        """,
        (eid, eid, eid, eid),
    ).fetchall()
    return [(r["eid"], r["freq"]) for r in rows]


class TestEntityMemoryAggregation:
    def test_memories_referencing_alice(self, entity_fixture):
        f = entity_fixture
        memories = _memories_for(f["conn"], f["alice"])
        ids = sorted(m["id"] for m in memories)
        # m1, m2, m4 reference alice; m3 does not
        assert ids == sorted([f["m1"], f["m2"], f["m4"]])

    def test_memory_excludes_unreferenced(self, entity_fixture):
        f = entity_fixture
        memories = _memories_for(f["conn"], f["alice"])
        ids = [m["id"] for m in memories]
        assert f["m3"] not in ids


class TestCoOccurrence:
    def test_alice_co_occurs_symmetrically(self, entity_fixture):
        f = entity_fixture
        co = dict(_co_occurring_for(f["conn"], f["alice"]))
        # alice in m1 (with bob), m2 (with charlie), m4 (alone) → 1 each
        assert co.get(f["bob"]) == 1
        assert co.get(f["charlie"]) == 1
        # Self-exclusion is the load-bearing part
        assert f["alice"] not in co

    def test_charlie_co_occurs_with_alice_and_bob(self, entity_fixture):
        f = entity_fixture
        co = dict(_co_occurring_for(f["conn"], f["charlie"]))
        assert co.get(f["alice"]) == 1
        assert co.get(f["bob"]) == 1
        assert f["charlie"] not in co

    def test_isolated_entity_has_no_cooccurrences(self, fresh_db):
        eid = crud.create_entity(fresh_db, canonical_name="isolated",
                                  entity_type="concept")
        co = _co_occurring_for(fresh_db, eid)
        assert co == []


class TestRelationsList:
    def test_relations_returned_for_entity(self, entity_fixture):
        f = entity_fixture
        rels = crud.list_relations_for_node(f["conn"], f["alice"], "entities")
        assert len(rels) == 1
        assert rels[0]["edge_type"] == "related_to"
        # alice → bob
        assert rels[0]["target_id"] == f["bob"]
