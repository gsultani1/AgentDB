"""swadb - A Sovereign Agent Memory System.

The PyPI package and the product are both named ``swadb``.

Most users interact with this package via the CLI (``swadb init``,
``swadb serve``, ``swadb mcp``). For embedding the memory layer
directly inside a Python application, this top-level module re-exports
the minimum primitives needed to open a database and call the CRUD
layer:

    from swadb import initialize_database, get_connection, crud

    conn = initialize_database("my.db")
    mid = crud.create_short_term_memory(conn, "hello", source="test")

Everything else — embeddings, the 9-stage retrieval pipeline, MCP
server, HTTP server — lives in its own submodule and is imported
explicitly when needed (e.g. ``from swadb.embeddings import
generate_embedding``).
"""

from . import crud
from swadb.database import (
    initialize_database,
    get_connection,
    verify_schema,
)

__version__ = "0.2.0"
__author__ = "George Sultani"
__license__ = "Apache-2.0"
__url__ = "https://github.com/gsultani1/AgentDB"

__all__ = [
    "initialize_database",
    "get_connection",
    "verify_schema",
    "crud",
    "__version__",
    "__author__",
    "__license__",
    "__url__",
]
