"""
Batch memory ops: end-to-end through the same shapes the HTTP handlers
build. Catches the impedance mismatch between handler body and CRUD
signature that bit us in commit b6426bf.
"""
import pytest
from swadb import crud


def _seed(conn, n=5):
    return [
        crud.create_short_term_memory(conn, f"memory {i}", "conversation")
        for i in range(n)
    ]


class TestBatchPin:
    def test_pin_creates_one_pin_row_per_id(self, fresh_db):
        ids = _seed(fresh_db, 3)
        pairs = [(i, "short_term_memory") for i in ids]
        crud.batch_pin_memories(fresh_db, pairs)
        n = fresh_db.execute("SELECT COUNT(*) FROM pinned_memories").fetchone()[0]
        assert n == 3


class TestBatchTag:
    def test_tag_creates_one_assignment_per_id(self, fresh_db):
        ids = _seed(fresh_db, 4)
        tag_id = crud.create_tag(fresh_db, "important")
        pairs = [(i, "short_term_memory") for i in ids]
        crud.batch_tag_memories(fresh_db, pairs, tag_id)
        n = fresh_db.execute(
            "SELECT COUNT(*) FROM tag_assignments WHERE tag_id = ?", (tag_id,)
        ).fetchone()[0]
        assert n == 4

    def test_tag_lookup_or_create_idiom(self, fresh_db):
        """Mirror what the HTTP handler does: find_tag_by_name first, create
        if missing. This is the path the UI takes."""
        ids = _seed(fresh_db, 2)
        existing = crud.find_tag_by_name(fresh_db, "newtag")
        assert existing is None
        tag_id = crud.create_tag(fresh_db, "newtag")
        pairs = [(i, "short_term_memory") for i in ids]
        crud.batch_tag_memories(fresh_db, pairs, tag_id)
        # Second time around, find_tag_by_name returns the existing one
        existing = crud.find_tag_by_name(fresh_db, "newtag")
        assert existing is not None
        assert existing["id"] == tag_id


class TestBatchPromote:
    def test_short_to_mid_creates_mtm_rows(self, fresh_db):
        ids = _seed(fresh_db, 3)
        promoted = crud.batch_promote_memories(fresh_db, ids, "short")
        assert len(promoted) == 3
        assert fresh_db.execute("SELECT COUNT(*) FROM midterm_memory").fetchone()[0] == 3

    def test_short_to_mid_marks_source_promoted(self, fresh_db):
        ids = _seed(fresh_db, 3)
        crud.batch_promote_memories(fresh_db, ids, "short")
        n = fresh_db.execute(
            "SELECT COUNT(*) FROM short_term_memory WHERE status = 'promoted'"
        ).fetchone()[0]
        assert n == 3

    def test_mid_to_long(self, fresh_db):
        # Seed 2 MTM rows directly
        m1 = crud.create_midterm_memory(fresh_db, "mid1", confidence=0.7)
        m2 = crud.create_midterm_memory(fresh_db, "mid2", confidence=0.8)
        promoted = crud.batch_promote_memories(fresh_db, [m1, m2], "mid")
        assert len(promoted) == 2
        assert fresh_db.execute("SELECT COUNT(*) FROM long_term_memory").fetchone()[0] == 2


class TestBatchDelete:
    def test_stm_soft_deleted(self, fresh_db):
        ids = _seed(fresh_db, 3)
        pairs = [(i, "short_term_memory") for i in ids]
        crud.batch_delete_memories(fresh_db, pairs)
        # Soft delete: rows still exist but status='expired'
        total = fresh_db.execute(
            "SELECT COUNT(*) FROM short_term_memory"
        ).fetchone()[0]
        expired = fresh_db.execute(
            "SELECT COUNT(*) FROM short_term_memory WHERE status = 'expired'"
        ).fetchone()[0]
        assert total == 3
        assert expired == 3

    def test_mtm_hard_deleted(self, fresh_db):
        m1 = crud.create_midterm_memory(fresh_db, "mid1", confidence=0.5)
        m2 = crud.create_midterm_memory(fresh_db, "mid2", confidence=0.5)
        pairs = [(m1, "midterm_memory"), (m2, "midterm_memory")]
        crud.batch_delete_memories(fresh_db, pairs)
        assert fresh_db.execute("SELECT COUNT(*) FROM midterm_memory").fetchone()[0] == 0
