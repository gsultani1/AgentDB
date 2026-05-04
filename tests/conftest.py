"""
Shared pytest fixtures for the swadb test suite.

Most tests want a fresh, plaintext, schema-initialized database. The
`fresh_db` fixture builds one in a per-test tempdir so tests don't pollute
each other and there's nothing to clean up between runs.
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

# Allow running pytest from the repo root without installing the package.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


@pytest.fixture
def tmp_db_path(tmp_path):
    """Per-test tempdir with a target DB path. tmp_path is a pytest builtin."""
    return str(tmp_path / "swadb-test.db")


@pytest.fixture
def fresh_db(tmp_db_path):
    """
    Initialized plaintext SQLite connection in a per-test tempdir. Closes
    on teardown. Use this when you need to call CRUD or feature functions
    that take a `conn`.
    """
    from swadb.database import initialize_database
    conn = initialize_database(tmp_db_path)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


@pytest.fixture
def reset_runtime_passphrase():
    """
    Encryption tests touch the module-level _RUNTIME_PASSPHRASE in
    swadb.database. This fixture clears it before AND after the test so a
    leak from one test doesn't change the behavior of another.
    """
    from swadb.database import clear_runtime_passphrase
    clear_runtime_passphrase()
    yield
    clear_runtime_passphrase()


def _has_sqlcipher():
    try:
        import sqlcipher3  # noqa: F401
        return True
    except ImportError:
        try:
            import pysqlcipher3  # noqa: F401
            return True
        except ImportError:
            return False


# Marker auto-skip: encryption tests get skipped when sqlcipher3 isn't
# installed, since the underlying encrypt/decrypt operations require it.
def pytest_collection_modifyitems(config, items):
    if _has_sqlcipher():
        return
    skip_enc = pytest.mark.skip(reason="sqlcipher3 not installed; encryption tests skipped")
    for item in items:
        if "encryption" in item.keywords:
            item.add_marker(skip_enc)
