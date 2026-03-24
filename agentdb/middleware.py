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
            content = msg["content"]
            # Support multi-part content (text + images)
            if isinstance(content, list):
                msg_content = content  # Already in Claude format [{type: "text/image", ...}]
            else:
                msg_content = content
            api_messages.append({"role": msg["role"], "content": msg_content})

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
            content = msg["content"]
            # Support multi-part content (text + images)
            if isinstance(content, list):
                msg_content = content
            else:
                msg_content = content
            api_messages.append({"role": msg["role"], "content": msg_content})

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


class OllamaAdapter(ProviderAdapter):
    """Adapter for Ollama local server (HTTP to /api/chat)."""

    def format_context(self, context_payload):
        return LocalLLMAdapter().format_context(context_payload)

    def call_provider(self, messages, formatted_context, config):
        import urllib.request

        base_url = config.get("llm_endpoint", "http://localhost:11434")
        endpoint = base_url.rstrip("/")
        if not endpoint.endswith("/api/chat"):
            endpoint += "/api/chat"
        model = config.get("llm_model", "llama3")

        api_messages = [{"role": "system", "content": formatted_context}]
        for msg in messages:
            api_messages.append({"role": msg["role"], "content": msg["content"]})

        payload = {"model": model, "messages": api_messages, "stream": False}

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("message", {}).get("content", str(result))


class LlamaCppAdapter(ProviderAdapter):
    """Adapter for llama.cpp server (OpenAI-compatible /v1/chat/completions)."""

    def format_context(self, context_payload):
        return OpenAIAdapter().format_context(context_payload)

    def call_provider(self, messages, formatted_context, config):
        import urllib.request

        base_url = config.get("llm_endpoint", "http://localhost:8080")
        endpoint = base_url.rstrip("/")
        if not endpoint.endswith("/v1/chat/completions"):
            endpoint += "/v1/chat/completions"
        model = config.get("llm_model", "default")

        api_messages = [{"role": "system", "content": formatted_context}]
        for msg in messages:
            api_messages.append({"role": msg["role"], "content": msg["content"]})

        payload = {"model": model, "messages": api_messages, "max_tokens": 4096}
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]


class LMStudioAdapter(ProviderAdapter):
    """Adapter for LM Studio (OpenAI-compatible endpoint)."""

    def format_context(self, context_payload):
        return OpenAIAdapter().format_context(context_payload)

    def call_provider(self, messages, formatted_context, config):
        import urllib.request

        base_url = config.get("llm_endpoint", "http://localhost:1234")
        endpoint = base_url.rstrip("/")
        if not endpoint.endswith("/v1/chat/completions"):
            endpoint += "/v1/chat/completions"
        model = config.get("llm_model", "default")

        api_messages = [{"role": "system", "content": formatted_context}]
        for msg in messages:
            api_messages.append({"role": msg["role"], "content": msg["content"]})

        payload = {"model": model, "messages": api_messages, "max_tokens": 4096}
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]


class CustomAdapter(ProviderAdapter):
    """Adapter for any OpenAI-compatible /v1/chat/completions endpoint."""

    def format_context(self, context_payload):
        return OpenAIAdapter().format_context(context_payload)

    def call_provider(self, messages, formatted_context, config):
        import urllib.request

        endpoint = config.get("llm_endpoint", "")
        if not endpoint:
            raise ValueError("Custom provider requires an endpoint URL")
        api_key = config.get("llm_api_key", "")
        model = config.get("llm_model", "default")

        api_messages = [{"role": "system", "content": formatted_context}]
        for msg in messages:
            api_messages.append({"role": msg["role"], "content": msg["content"]})

        payload = {"model": model, "messages": api_messages, "max_tokens": 4096}
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]


ADAPTERS = {
    "claude": ClaudeAdapter,
    "openai": OpenAIAdapter,
    "local": LocalLLMAdapter,
    "ollama": OllamaAdapter,
    "llamacpp": LlamaCppAdapter,
    "lmstudio": LMStudioAdapter,
    "custom": CustomAdapter,
}


def get_adapter(provider_name):
    """
    Get the adapter class for a provider name.

    Args:
        provider_name: str, one of the registered provider types.

    Returns:
        ProviderAdapter instance.
    """
    cls = ADAPTERS.get(provider_name)
    if cls is None:
        # Fall back to custom adapter for unknown types
        cls = CustomAdapter
    return cls()


def get_llm_config(conn, provider_id=None, agent_id=None):
    """
    Load LLM config using v1.5 provider resolution priority chain:
    1. Explicit provider_id in request
    2. Agent's default_provider_id
    3. active_provider_id in meta_config
    4. First is_default=1 row in llm_providers
    5. First is_active=1 row in llm_providers
    6. Flat meta_config keys (legacy fallback)
    """
    def _provider_to_config(prov):
        prov = dict(prov) if not isinstance(prov, dict) else prov
        return {
            "llm_provider": prov.get("provider_type", "claude"),
            "llm_api_key": prov.get("api_key") or "",
            "llm_model": prov.get("model", ""),
            "llm_endpoint": prov.get("endpoint") or "",
            "provider_id": prov.get("id"),
            "context_window_tokens": prov.get("context_window_tokens", 200000),
            "max_output_tokens": prov.get("max_output_tokens", 4096),
            "temperature": prov.get("temperature", 0.7),
            "system_prompt_prefix": prov.get("system_prompt_prefix") or "",
        }

    try:
        # 1. Explicit provider_id
        if provider_id:
            prov = conn.execute("SELECT * FROM llm_providers WHERE id = ?",
                                (provider_id,)).fetchone()
            if prov:
                return _provider_to_config(prov)

        # 2. Agent's default_provider_id
        if agent_id:
            agent = conn.execute("SELECT default_provider_id FROM agents WHERE id = ?",
                                 (agent_id,)).fetchone()
            if agent and agent["default_provider_id"]:
                prov = conn.execute("SELECT * FROM llm_providers WHERE id = ?",
                                    (agent["default_provider_id"],)).fetchone()
                if prov:
                    return _provider_to_config(prov)

        # 3. active_provider_id in meta_config
        active_id = crud.get_config_value(conn, "active_provider_id")
        if active_id:
            prov = conn.execute("SELECT * FROM llm_providers WHERE id = ?",
                                (active_id,)).fetchone()
            if prov:
                return _provider_to_config(prov)

        # 4. First is_default=1 row
        prov = conn.execute(
            "SELECT * FROM llm_providers WHERE is_default = 1 LIMIT 1"
        ).fetchone()
        if prov:
            return _provider_to_config(prov)

        # 5. First is_active=1 row
        prov = conn.execute(
            "SELECT * FROM llm_providers WHERE is_active = 1 ORDER BY created_at LIMIT 1"
        ).fetchone()
        if prov:
            return _provider_to_config(prov)
    except Exception:
        pass

    # 6. Flat meta_config keys (legacy fallback)
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


def execute_chat_pipeline(conn, user_message, session_id=None, messages_history=None,
                          agent_id=None, provider_override=None, model_override=None,
                          provider_id=None):
    """
    Full chat pipeline: retrieve context, call LLM, ingest exchange, return observability payload.

    Args:
        conn: sqlite3.Connection
        user_message: str, the user's message.
        session_id: str, active session ID.
        messages_history: list of previous {"role", "content"} dicts (optional).
        agent_id: str, scope retrieval and ingestion to this agent (optional).
        provider_override: str, override the configured LLM provider type (optional).
        model_override: str, override the configured model name (optional).
        provider_id: str, explicit provider ID from providers table (optional).

    Returns:
        dict with keys: response, context_payload, snapshot_id, ingested_ids
    """
    if messages_history is None:
        messages_history = []

    # Load provider config using v1.5 resolution chain
    effective_provider_id = provider_id or provider_override
    llm_config = get_llm_config(conn, provider_id=effective_provider_id, agent_id=agent_id)
    provider_name = llm_config.get("llm_provider", "claude")
    if provider_override and provider_override in ADAPTERS:
        provider_name = provider_override
    if model_override:
        llm_config["llm_model"] = model_override

    # Update last_used on the provider
    if llm_config.get("provider_id"):
        try:
            conn.execute("UPDATE llm_providers SET last_used = ? WHERE id = ?",
                         (datetime.utcnow().isoformat(), llm_config["provider_id"]))
            conn.commit()
        except Exception:
            pass

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
