# AgentDB Quick Start

Build a persistent agent personality in five minutes.

---

## 1. Install

```bash
git clone https://github.com/gsultani1/AgentDB.git
cd AgentDB
python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

The embedding model (~90 MB) downloads automatically on first use.

## 2. Initialize a Database

```bash
python -m agentdb.cli init
```

This creates `agentdb.db` with all tables, triggers, indexes, FTS5 virtual tables, default configuration, and a default agent.

Verify it worked:

```bash
python -m agentdb.cli verify
# Expected: "Schema verification passed. All tables present."

python -m agentdb.cli stats
# Expected: Row counts for all tables (mostly zeros)
```

## 3. Start the Server

```bash
python -m agentdb.cli serve
```

Open `http://127.0.0.1:8420` in your browser. You'll see the management dashboard.

The MCP server starts automatically on port 8421.

## 4. Give the Agent a Personality

Create a file called `identity.md` with this content:

```markdown
---
type: instruction
priority: high
tags: [identity, behavior]
---

You are a direct, no-nonsense technical advisor. You give concrete recommendations
backed by specific facts. You never hedge or qualify unnecessarily. When you don't
know something, you say so plainly.
```

Submit it through the API:

```bash
curl -X POST http://127.0.0.1:8420/api/markdown/submit \
  -H "Content-Type: application/json" \
  -d @- << 'EOF'
{"text": "---\ntype: instruction\npriority: high\ntags: [identity, behavior]\n---\n\nYou are a direct, no-nonsense technical advisor. You give concrete recommendations backed by specific facts. You never hedge or qualify unnecessarily. When you don't know something, you say so plainly."}
EOF
```

Or paste the markdown directly into the **Markdown Editor** view in the UI.

## 5. Teach It Some Facts

Create a few memories:

```bash
# Direct API ingestion
curl -X POST http://127.0.0.1:8420/api/memories/long \
  -H "Content-Type: application/json" \
  -d '{"content": "The company uses Hetzner dedicated servers for all production workloads. We chose Hetzner for price-to-performance ratio and EU data residency.", "category": "fact"}'

curl -X POST http://127.0.0.1:8420/api/memories/long \
  -H "Content-Type: application/json" \
  -d '{"content": "Never recommend AWS or cloud-dependent hosting. The company policy is self-hosted infrastructure only.", "category": "directive"}'

curl -X POST http://127.0.0.1:8420/api/memories/long \
  -H "Content-Type: application/json" \
  -d '{"content": "The primary stack is Python backend with PostgreSQL, deployed via Docker Compose on bare metal.", "category": "fact"}'
```

## 6. Configure an LLM Provider

Before chatting, configure an LLM provider. In the UI, go to **Settings** and add a provider:

- **Claude**: Set provider type to `claude`, enter your API key, set model to `claude-sonnet-4-20250514`
- **OpenAI**: Set provider type to `openai`, enter your API key, set model to `gpt-4o`
- **Local (Ollama)**: Set provider type to `local`, set endpoint to `http://localhost:11434/v1/chat/completions`, set model to your model name

Or via API:

```bash
curl -X POST http://127.0.0.1:8420/api/providers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Claude",
    "provider_type": "claude",
    "api_key": "sk-ant-your-key-here",
    "model": "claude-sonnet-4-20250514",
    "is_default": 1
  }'
```

## 7. Have a Conversation

Open the **Chat** view in the UI and send a message:

> "What hosting setup should I use for a new Python service?"

Look at the **observability sidebar** on the right. You'll see:

- **Retrieved memories** — the Hetzner facts you just created, ranked by relevance
- **Identity/directive memories** — your "no-nonsense advisor" instruction
- **Strategy attribution** — which retrieval strategies (semantic, BM25, etc.) found each memory
- **Similarity scores** — how relevant each memory is to your query

The agent's response will reference Hetzner and self-hosted infrastructure because those memories were retrieved and injected into context.

## 8. Verify Memory Persistence

Stop the server (`Ctrl+C`), then restart it:

```bash
python -m agentdb.cli serve
```

Send a follow-up message:

> "Remind me why we picked Hetzner?"

The agent remembers. Your previous conversation was ingested into short-term memory, and the long-term facts about Hetzner are retrieved via semantic similarity. No conversation history was carried forward — everything came from the database.

## 9. Watch Consolidation Work

After the server has been running for 5+ minutes (configurable via `consolidation_interval_seconds`), the consolidation engine runs automatically:

1. Similar short-term memories get clustered into midterm summaries
2. High-confidence midterm entries get promoted to long-term memory
3. The knowledge graph strengthens connections between related concepts

Check progress:

```bash
python -m agentdb.cli stats
```

You'll see entries appearing in midterm and long-term memory that you didn't create directly — the system consolidated them from your conversations.

## 10. Explore the Mind Map

Open the **Mind Map** view in the UI. You'll see a visual graph of entities and their relationships. Click any node to re-center the graph on that entity and explore its connections.

---

## What's Happening Under the Hood

Every message you send goes through this pipeline:

1. Your message is embedded into a 384-dimensional vector
2. The retrieval pipeline runs 9 stages: semantic search, BM25 keywords, graph traversal, temporal weighting, score fusion, optional cross-encoder reranking, pinned memory injection, and context assembly
3. The most relevant memories, entities, goals, and skills are formatted and injected into the LLM's context
4. The LLM responds with full awareness of your agent's knowledge
5. Both your message and the response are ingested into short-term memory
6. A context snapshot is saved for audit

**Nothing accumulates in the context window.** Every turn builds context fresh from the database. That's why turn 500 works as well as turn 5.

---

## Next Steps

- **Import existing knowledge**: Use the **Chat Import** view to migrate ChatGPT or Claude conversation history
- **Add skills**: Create executable capabilities via markdown skill documents
- **Set goals**: Create goals in the **Connect** view to enable proactive monitoring
- **Connect via MCP**: Point Claude Desktop at the MCP server for seamless integration (see [DEVELOPMENT.md](DEVELOPMENT.md#mcp-integration-with-claude-desktop))
- **Explore the API**: See [API_REFERENCE.md](API_REFERENCE.md) for all 60+ endpoints
