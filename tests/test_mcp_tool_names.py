"""
Guard the MCP tool names against drift from the documentation.

The retrieval tool's Python function is `retrieve_context_tool` (it can't
shadow the `retrieve_context` import from swadb.context), but the tool is
registered — and documented in README.md, docs/API_REFERENCE.md, and
api_documentation/mcp.md — as `retrieve_context`. This test pins the
registered names so a rename in either direction shows up in CI.
"""
import anyio
import pytest

mcp_server = pytest.importorskip("swadb.mcp_server",
                                 reason="mcp package not installed")

DOCUMENTED_TOOLS = {
    "retrieve_context",
    "ingest_memory",
    "search_memories",
    "list_memories",
    "create_entity",
    "list_entities",
    "check_goals",
    "get_health",
    "run_consolidation",
}


def _registered_tool_names():
    tools = anyio.run(mcp_server.mcp.list_tools)
    return {t.name for t in tools}


def test_documented_tools_registered():
    names = _registered_tool_names()
    missing = DOCUMENTED_TOOLS - names
    assert not missing, f"documented MCP tools missing from registry: {sorted(missing)}"


def test_no_internal_suffix_leaks():
    names = _registered_tool_names()
    assert "retrieve_context_tool" not in names, (
        "the retrieval tool must be registered under its documented name "
        "'retrieve_context', not the internal function name"
    )
