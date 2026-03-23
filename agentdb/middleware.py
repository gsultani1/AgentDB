"""
Provider-agnostic LLM middleware for AgentDB.

Implements the middleware pattern from PRD Section 6.3:
1. Receive user message
2. Query AgentDB for context
3. Construct provider-specific API request with context injected
4. Send request to provider
5. Receive response
6. Ingest both user message and AI response into AgentDB
7. Return response with observability payload

Provider adapters are pluggable Python modules with two methods:
- format_context(context_payload) -> str
- call_provider(messages, formatted_context, config) -> str
"""

import json
import time
from datetime import datetime

from agentdb import crud
from agentdb.context import retrieve_context
from agentdb.embeddings import generate_embedding, embedding_to_blob


class ProviderAdapter:
    """Base class for LLM provider adapters."""

    def format_context(self, context_payload):
        """
        Format AgentDB context for injection into the provider's API.

        Args:
            context_payload: dict from retrieve_context()

        Returns:
            str: Provider-ready context string.
        """
        raise NotImplementedError

    def call_provider(self, messages, formatted_context, config):
        """
        Send a request to the LLM provider.

        Args:
            messages: list of {"role": str, "content": str} dicts.
            formatted_context: str from format_context().
            config: dict with provider-specific settings.

        Returns:
            str: The AI response text.
        """
        raise NotImplementedError


class ClaudeAdapter(ProviderAdapter):
    """Adapter for Anthropic Claude API."""

    def format_context(self, context_payload):
        parts = []
        parts.append("<agentdb_context>")

        # Identity/directive memories
        if context_payload.get("identity"):
            parts.append("<identity>")
            for mem in context_payload["identity"]:
                parts.append(f"  <directive>{mem['content']}</directive>")
            parts.append("</identity>")

        # Retrieved memories
        memories = context_payload.get("memories", {})
        if any(memories.values()):
            parts.append("<memories>")
            for tier, mems in memories.items():
                for mem in mems:
                    parts.append(
                        f'  <memory tier="{tier}" confidence="{mem.get("confidence", "N/A")}" '
                        f'score="{mem.get("similarity_score", 0)}">'
                    )
                    parts.append(f"    {mem['content']}")
                    parts.append("  </memory>")
            parts.append("</memories>")

        # Matched goals
        goals = context_payload.get("goals", [])
        if goals:
            parts.append("<active_goals>")
            for g in goals:
                parts.append(
                    f'  <goal priority="{g.get("priority", 0)}" '
                    f'score="{g.get("similarity_score", 0)}">'
                )
                parts.append(f"    {g['description']}")
                parts.append("  </goal>")
            parts.append("</active_goals>")

        # Matched skills
        skills = context_payload.get("skills", [])
        if skills:
            parts.append("<available_skills>")
            for s in skills:
                parts.append(
                    f'  <skill name="{s["name"]}" type="{s["execution_type"]}" '
                    f'score="{s.get("similarity_score", 0)}">'
                )
                parts.append(f"    {s['description']}")
                parts.append("  </skill>")
            parts.append("</available_skills>")

        # Entities
        entities = context_payload.get("entities", [])
        if entities:
            parts.append("<entities>")
            for e in entities:
                parts.append(
                    f'  <entity name="{e["canonical_name"]}" type="{e["entity_type"]}">'
                )
                if e.get("aliases"):
                    aliases = e["aliases"]
                    if isinstance(aliases, str):
                        aliases = json.loads(aliases)
                    parts.append(f"    Aliases: {', '.join(aliases)}")
                parts.append("  </entity>")
            parts.append("</entities>")

        parts.append("</agentdb_context>")
        return "\n".join(parts)

    def call_provider(self, messages, formatted_context, config):
        import urllib.request

        api_key = config.get("llm_api_key", "")
        model = config.get("llm_model", "claude-sonnet-4-20250514")
        endpoint = config.get("llm_endpoint", "https://api.anthropic.com/v1/messages")

        system_prompt = formatted_context

        api_messages = []
        for msg in messages:
            api_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        payload = {
            "model": model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": api_messages,
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["content"][0]["text"]


class OpenAIAdapter(ProviderAdapter):
    """Adapter for OpenAI-compatible APIs."""

    def format_context(self, context_payload):
        parts = []
        parts.append("## AgentDB Context\n")

        if context_payload.get("identity"):
            parts.append("### Identity & Directives")
            for mem in context_payload["identity"]:
                parts.append(f"- {mem['content']}")
            parts.append("")

        memories = context_payload.get("memories", {})
        if any(memories.values()):
            parts.append("### Retrieved Memories")
            for tier, mems in memories.items():
                for mem in mems:
                    conf = mem.get("confidence", "N/A")
                    parts.append(
                        f"- [{tier}|conf:{conf}|score:{mem.get('similarity_score', 0)}] "
                        f"{mem['content']}"
                    )
            parts.append("")

        goals = context_payload.get("goals", [])
        if goals:
            parts.append("### Active Goals")
            for g in goals:
                parts.append(f"- [priority:{g.get('priority', 0)}] {g['description']}")
            parts.append("")

        skills = context_payload.get("skills", [])
        if skills:
            parts.append("### Available Skills")
            for s in skills:
                parts.append(f"- {s['name']} ({s['execution_type']}): {s['description']}")
            parts.append("")

        entities = context_payload.get("entities", [])
        if entities:
            parts.append("### Known Entities")
            for e in entities:
                parts.append(f"- {e['canonical_name']} ({e['entity_type']})")
            parts.append("")

        return "\n".join(parts)

    def call_provider(self, messages, formatted_context, config):
        import urllib.request

        api_key = config.get("llm_api_key", "")
        model = config.get("llm_model", "gpt-4o")
        endpoint = config.get(
            "llm_endpoint", "https://api.openai.com/v1/chat/completions"
        )

        api_messages = [{"role": "system", "content": formatted_context}]
        for msg in messages:
            api_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        payload = {
            "model": model,
            "messages": api_messages,
            "max_tokens": 4096,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]


class LocalLLMAdapter(ProviderAdapter):
    """Adapter for local LLM servers (Ollama, llama.cpp, vLLM, etc.)."""

    def format_context(self, context_payload):
        parts = []
        parts.append("[AgentDB Context]")

        if context_payload.get("identity"):
            parts.append("\n[Identity & Directives]")
            for mem in context_payload["identity"]:
                parts.append(mem["content"])

        memories = context_payload.get("memories", {})
        if any(memories.values()):
            parts.append("\n[Retrieved Memories]")
            for tier, mems in memories.items():
                for mem in mems:
                    parts.append(f"({tier}) {mem['content']}")

        goals = context_payload.get("goals", [])
        if goals:
            parts.append("\n[Active Goals]")
            for g in goals:
                parts.append(f"- {g['description']}")

        skills = context_payload.get("skills", [])
        if skills:
            parts.append("\n[Available Skills]")
            for s in skills:
                parts.append(f"- {s['name']}: {s['description']}")

        return "\n".join(parts)

    def call_provider(self, messages, formatted_context, config):
        import urllib.request

        endpoint = config.get("llm_endpoint", "http://localhost:11434/api/chat")
        model = config.get("llm_model", "llama3")

        api_messages = [{"role": "system", "content": formatted_context}]
        for msg in messages:
            api_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        payload = {
            "model": model,
            "messages": api_messages,
            "stream": False,
        }

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            # Ollama format
            if "message" in result:
                return result["message"]["content"]
            # OpenAI-compatible format
            if "choices" in result:
                return result["choices"][0]["message"]["content"]
            return str(result)


ADAPTERS = {
    "claude": ClaudeAdapter,
    "openai": OpenAIAdapter,
    "local": LocalLLMAdapter,
}


def get_adapter(provider_name):
    """
    Get the adapter class for a provider name.

    Args:
        provider_name: str, one of 'claude', 'openai', 'local'.

    Returns:
        ProviderAdapter instance.
    """
    cls = ADAPTERS.get(provider_name)
    if cls is None:
        raise ValueError(f"Unknown LLM provider: {provider_name}. Available: {list(ADAPTERS.keys())}")
    return cls()


def get_llm_config(conn):
    """Load LLM-related config from meta_config."""
    keys = ["llm_provider", "llm_api_key", "llm_model", "llm_endpoint"]
    config = {}
    for key in keys:
        val = crud.get_config_value(conn, key)
        if val is not None:
            config[key] = val
    return config


def get_identity_memories(conn, agent_id=None):
    """Retrieve identity and directive long-term memories, scoped to agent_id + 'shared'."""
    if agent_id:
        rows = conn.execute(
            "SELECT * FROM long_term_memory "
            "WHERE category IN ('identity', 'directive') "
            "AND (agent_id = ? OR agent_id = 'shared')",
            (agent_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM long_term_memory WHERE category IN ('identity', 'directive')"
        ).fetchall()
    result = []
    for row in rows:
        entry = dict(row)
        entry.pop("embedding", None)
        result.append(entry)
    return result


def execute_chat_pipeline(conn, user_message, session_id, messages_history=None, agent_id=None):
    """
    Full chat pipeline: retrieve context, call LLM, ingest exchange, return observability payload.

    Args:
        conn: sqlite3.Connection
        user_message: str, the user's message.
        session_id: str, active session ID.
        messages_history: list of previous {"role", "content"} dicts (optional).
        agent_id: str, scope retrieval and ingestion to this agent (optional).

    Returns:
        dict with keys: response, context_payload, snapshot_id, ingested_ids
    """
    if messages_history is None:
        messages_history = []

    # Load provider config
    llm_config = get_llm_config(conn)
    provider_name = llm_config.get("llm_provider", "claude")
    adapter = get_adapter(provider_name)

    # Retrieve context
    context_payload = retrieve_context(conn, user_message, agent_id=agent_id)

    # Add identity memories to context payload (scoped to agent)
    identity = get_identity_memories(conn, agent_id=agent_id)
    context_payload["identity"] = identity

    # Format context for the provider
    formatted_context = adapter.format_context(context_payload)

    # Build messages list
    messages = list(messages_history)
    messages.append({"role": "user", "content": user_message})

    # Call LLM provider
    start_time = time.time()
    try:
        ai_response = adapter.call_provider(messages, formatted_context, llm_config)
        llm_latency = round(time.time() - start_time, 3)
        llm_error = None
    except Exception as e:
        ai_response = f"[LLM Error: {str(e)}]"
        llm_latency = round(time.time() - start_time, 3)
        llm_error = str(e)

    # Ingest user message and AI response
    ingest_agent = agent_id or "default"
    user_emb = embedding_to_blob(generate_embedding(user_message))
    user_mem_id = crud.create_short_term_memory(
        conn, user_message, "conversation",
        embedding=user_emb, session_id=session_id, agent_id=ingest_agent,
    )
    ai_emb = embedding_to_blob(generate_embedding(ai_response))
    ai_mem_id = crud.create_short_term_memory(
        conn, ai_response, "conversation",
        embedding=ai_emb, session_id=session_id, agent_id=ingest_agent,
    )

    # Create context snapshot
    memory_ids = []
    for tier, mems in context_payload.get("memories", {}).items():
        for m in mems:
            memory_ids.append({"id": m["id"], "table": _tier_to_table(tier)})

    skill_ids = [s["id"] for s in context_payload.get("skills", [])]
    goal_ids = [g["id"] for g in context_payload.get("goals", [])]

    snapshot_id = crud.create_context_snapshot(
        conn,
        trigger_description=user_message[:200],
        memory_ids=memory_ids,
        skill_ids=skill_ids,
        relation_ids=[],
        goal_id=goal_ids[0] if goal_ids else None,
        outcome=ai_response[:500],
    )

    return {
        "response": ai_response,
        "context_payload": context_payload,
        "formatted_context": formatted_context,
        "snapshot_id": snapshot_id,
        "ingested_ids": {
            "user_message": user_mem_id,
            "ai_response": ai_mem_id,
        },
        "provider": provider_name,
        "model": llm_config.get("llm_model", ""),
        "llm_latency_seconds": llm_latency,
        "llm_error": llm_error,
    }


def _tier_to_table(tier_label):
    """Convert tier label to table name."""
    mapping = {
        "short_term": "short_term_memory",
        "midterm": "midterm_memory",
        "long_term": "long_term_memory",
    }
    return mapping.get(tier_label, tier_label)
