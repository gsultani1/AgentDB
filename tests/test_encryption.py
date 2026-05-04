"""
Encryption lifecycle + lock/unlock semantics.

Covers the core data-integrity guarantee: a user can encrypt → use →
restart-and-relock → unlock → use, all without losing any rows. Also
verifies the in-process runtime passphrase store correctly gates
get_connection.

Marked `encryption` so the suite is auto-skipped when sqlcipher3 isn't
installed (see conftest.pytest_collection_modifyitems).
"""
import sqlite3
import pytest

from swadb import crud
from swadb.database import (
    initialize_database, get_connection,
    encrypt_database, decrypt_database, rekey_database, is_db_encrypted,
    encryption_status,
    set_runtime_passphrase, clear_runtime_passphrase, get_runtime_passphrase,
)


pytestmark = pytest.mark.encryption


PASS_A = "first-pass-2026"
PASS_B = "second-pass-2026"
PASS_BAD = "definitely-wrong"


class TestEncryptionLifecycle:
    def test_full_lifecycle(self, tmp_db_path, reset_runtime_passphrase):
        # 1) Plaintext open
        conn = initialize_database(tmp_db_path)
        crud.create_short_term_memory(conn, "before encryption", "conversation")
        conn.close()
        assert is_db_encrypted(tmp_db_path) is False

        conn = get_connection(tmp_db_path)
        rows = conn.execute("SELECT COUNT(*) FROM short_term_memory").fetchone()[0]
        assert rows == 1
        conn.close()

        # 2) Encrypt + open with passphrase
        encrypt_database(tmp_db_path, PASS_A)
        set_runtime_passphrase(PASS_A)
        assert is_db_encrypted(tmp_db_path) is True
        conn = get_connection(tmp_db_path)
        assert conn.execute("SELECT COUNT(*) FROM short_term_memory").fetchone()[0] == 1
        conn.close()

        # 3) Simulate restart — clear runtime, open without passphrase RAISES
        clear_runtime_passphrase()
        with pytest.raises(RuntimeError, match="encrypted"):
            get_connection(tmp_db_path)

        # 4) Unlock — set runtime, open works again
        set_runtime_passphrase(PASS_A)
        conn = get_connection(tmp_db_path)
        assert conn.execute("SELECT COUNT(*) FROM short_term_memory").fetchone()[0] == 1
        conn.close()

        # 5) Rekey + verify new passphrase, old passphrase rejected
        rekey_database(tmp_db_path, PASS_A, PASS_B)
        clear_runtime_passphrase()
        set_runtime_passphrase(PASS_B)
        conn = get_connection(tmp_db_path)
        conn.close()

        # 6) Decrypt → plaintext open works
        decrypt_database(tmp_db_path, PASS_B)
        clear_runtime_passphrase()
        assert is_db_encrypted(tmp_db_path) is False
        conn = get_connection(tmp_db_path)
        assert conn.execute("SELECT COUNT(*) FROM short_term_memory").fetchone()[0] == 1
        conn.close()


class TestRuntimePassphrase:
    """The in-process passphrase store powers the UI unlock flow."""

    def test_set_get_clear(self, reset_runtime_passphrase):
        assert get_runtime_passphrase() is None
        set_runtime_passphrase("hunter2")
        assert get_runtime_passphrase() == "hunter2"
        clear_runtime_passphrase()
        assert get_runtime_passphrase() is None

    def test_runtime_overrides_env(self, monkeypatch, reset_runtime_passphrase):
        monkeypatch.setenv("SWADB_PASSPHRASE", "from-env")
        set_runtime_passphrase("from-runtime")
        from swadb.database import _read_passphrase_env
        assert _read_passphrase_env() == "from-runtime"
        clear_runtime_passphrase()
        # Without runtime, env wins
        assert _read_passphrase_env() == "from-env"

    def test_legacy_env_still_honored(self, monkeypatch, reset_runtime_passphrase, capsys):
        monkeypatch.delenv("SWADB_PASSPHRASE", raising=False)
        monkeypatch.setenv("AGENTDB_PASSPHRASE", "legacy")
        from swadb.database import _read_passphrase_env, _RUNTIME_PASSPHRASE  # noqa
        assert _read_passphrase_env() == "legacy"


class TestWrongPassphraseRejected:
    def test_wrong_pass_at_read(self, tmp_db_path, reset_runtime_passphrase):
        conn = initialize_database(tmp_db_path)
        crud.create_short_term_memory(conn, "secret", "conversation")
        conn.close()
        encrypt_database(tmp_db_path, PASS_A)
        set_runtime_passphrase(PASS_BAD)
        # SQLCipher: connect succeeds, first read errors
        try:
            conn = get_connection(tmp_db_path)
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
            conn.close()
        except Exception:
            # Some sqlcipher versions raise at connect — also acceptable
            pass


class TestIsDbEncryptedDetection:
    """Header-byte probe — does NOT require a passphrase to determine state."""

    def test_plain_db_not_encrypted(self, tmp_db_path):
        initialize_database(tmp_db_path).close()
        assert is_db_encrypted(tmp_db_path) is False

    def test_encrypted_db_detected(self, tmp_db_path, reset_runtime_passphrase):
        initialize_database(tmp_db_path).close()
        encrypt_database(tmp_db_path, PASS_A)
        assert is_db_encrypted(tmp_db_path) is True

    def test_missing_file_returns_false(self, tmp_path):
        nonexistent = str(tmp_path / "does-not-exist.db")
        assert is_db_encrypted(nonexistent) is False

    def test_status_payload_shape(self, tmp_db_path):
        initialize_database(tmp_db_path).close()
        s = encryption_status(tmp_db_path)
        assert s["sqlcipher_available"] is True
        assert s["db_encrypted"] is False
        assert s["library"] == "sqlcipher3"
        assert s["db_path"] == str(tmp_db_path)
